import bottle
from gevent.local import local
from sakura.common.bottle import PicklableFileRequest
from sakura.hub.secrets import SecretsRegistry
from sakura.hub.web.transfers import Transfer

# object storing greenlet-local data
greenlet_env = local()

def get_context():
    return HubContext._instance

class HubContext(object):
    _instance = None
    SESSION_SECRETS_LIFETIME = 5
    PW_RECOVERY_SECRETS_LIFETIME = 10 * 60
    def __init__(self, db):
        self.db = db
        self.daemons = self.db.Daemon
        self.dataflows = self.db.Dataflow
        self.users = self.db.User
        self.sessions = self.db.Session
        self.op_classes = self.db.OpClass
        self.op_instances = self.db.OpInstance
        self.links = self.db.Link
        self.op_params = self.db.OpParam
        self.datastores = self.db.Datastore
        self.databases = self.db.Database
        self.tables = self.db.DBTable
        self.columns = self.db.DBColumn
        self.session_secrets = SecretsRegistry(
                        HubContext.SESSION_SECRETS_LIFETIME)
        self.pw_recovery_secrets = SecretsRegistry(
                        HubContext.PW_RECOVERY_SECRETS_LIFETIME)
        self.transfers = {}
        HubContext._instance = self
    @property
    def session(self):
        return self.sessions[greenlet_env.session_id]
    def new_session(self):
        return self.sessions.new_session(self)
    def get_session(self, session_secret):
        return self.session_secrets.get_obj(session_secret)
    def on_daemon_connect(self, api):
        daemon_info = api.get_daemon_info_serializable()
        daemon = self.daemons.restore_daemon(api = api, **daemon_info)
        return daemon.id
    def on_daemon_disconnect(self, daemon_id):
        self.daemons[daemon_id].connected = False
    def create_link(self, src_op_id, src_out_id, dst_op_id, dst_in_id):
        src_op = self.op_instances[src_op_id]
        dst_op = self.op_instances[dst_op_id]
        link = self.links.create_link(src_op, src_out_id, dst_op, dst_in_id)
        self.db.commit()    # refresh link id
        return link.id
    def get_possible_links(self, src_op_id, dst_op_id):
        src_op = self.op_instances[src_op_id]
        dst_op = self.op_instances[dst_op_id]
        return self.links.get_possible_links(src_op, dst_op)
    def serve_operator_file(self, op_id, filepath):
        op = self.op_instances.get(id = op_id)
        if op is None:
            return bottle.HTTPError(404, "No such operator instance.")
        request = PicklableFileRequest(bottle.request, filepath)
        resp = op.serve_file(request)
        if resp[0] == True:
            return bottle.HTTPResponse(*resp[1:])
        else:
            return bottle.HTTPError(*resp[1:])
    def generate_session_secret(self):
        return self.session_secrets.generate_secret(self.session)
    def start_transfer(self):
        transfer = Transfer()
        self.transfers[transfer.transfer_id] = transfer
        return transfer.transfer_id
    def get_transfer_status(self, transfer_id):
        status = self.transfers[transfer_id].get_status()
        if status['status'] == 'done':
            del self.transfers[transfer_id]
        return status
    def abort_transfer(self, transfer_id):
        status = self.transfers[transfer_id].get_status()
        if status['status'] == 'done':
            # transfer is already completed!
            del self.transfers[transfer_id]
        else:
            self.transfers[transfer_id].abort()
