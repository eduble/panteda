from sakura.common.tools import SimpleAttrContainer

class Link(SimpleAttrContainer):
    def pack(self):
        return dict(
            link_id = self.link_id,
            src_id = self.src_op.op_id,
            src_out_id = self.src_out_id,
            dst_id = self.dst_op.op_id,
            dst_in_id = self.dst_in_id,
            gui_data = self.gui_data
        )

QUERY_LINKS_FROM_DAEMON = """
SELECT l.*
FROM    Link l,
        OpInstance op1, OpInstance op2,
        OpClass cls1, OpClass cls2
WHERE   l.src_op_id = op1.op_id AND l.dst_op_id = op2.op_id
  AND   op1.cls_id = cls1.cls_id AND op2.cls_id = cls2.cls_id
  AND   (cls1.daemon_id = %(daemon_id)d OR cls2.daemon_id = %(daemon_id)d);
"""

class LinkRegistry(object):
    def __init__(self, db):
        self.db = db
        self.info_per_link_id = {}
    def restore_daemon_state(self, daemon_info, op_instances):
        sql = QUERY_LINKS_FROM_DAEMON % dict(
                    daemon_id = daemon_info.daemon_id)
        for link_id, src_op_id, src_out_id, dst_op_id, dst_in_id, gui_data in \
                self.db.execute(sql).fetchall():
            # if both operators are available, restore the link
            if src_op_id in op_instances and dst_op_id in op_instances:
                src_op = op_instances[src_op_id]
                dst_op = op_instances[dst_op_id]
                self.instanciate(link_id, src_op, src_out_id, dst_op, dst_in_id, gui_data)
    def create(self, src_op, src_out_id, dst_op, dst_in_id):
        self.db.insert('Link',
                    src_op_id = src_op.op_id,
                    src_out_id = src_out_id,
                    dst_op_id = dst_op.op_id,
                    dst_in_id = dst_in_id)
        self.db.commit()
        link_id = self.db.lastrowid
        self.instanciate(link_id, src_op, src_out_id, dst_op, dst_in_id)
        return link_id
    def instanciate(self, link_id, src_op, src_out_id, dst_op, dst_in_id, gui_data = None):
        dst_op.daemon.api.connect_operators(
                src_op.op_id, src_out_id, dst_op.op_id, dst_in_id)
        desc = Link(    link_id = link_id,
                        src_op = src_op,
                        src_out_id = src_out_id,
                        dst_op = dst_op,
                        dst_in_id = dst_in_id,
                        gui_data = gui_data)
        self.info_per_link_id[link_id] = desc
        src_op.attached_links.add(link_id)
        dst_op.attached_links.add(link_id)
    def delete(self, link_id):
        link = self.info_per_link_id[link_id]
        src_op = link.src_op
        dst_op = link.dst_op
        dst_op.daemon.api.disconnect_operators(
            src_op.op_id, link.src_out_id, dst_op.op_id, link.dst_in_id)
        del self.info_per_link_id[link_id]
        src_op.attached_links.remove(link_id)
        dst_op.attached_links.remove(link_id)
        self.db.delete('Link', link_id = link_id)
    def get_possible_links(self, src_op, dst_op):
        # list possible new links
        possible_links = dst_op.daemon.api.get_possible_links(src_op.op_id, dst_op.op_id)
        # add existing links
        for l in self.info_per_link_id.values():
            if l.src_op.op_id == src_op.op_id and l.dst_op.op_id == dst_op.op_id:
                possible_links += ((l.src_out_id, l.dst_in_id),)
        return possible_links
    def __getitem__(self, link_id):
        return self.info_per_link_id[link_id]
    def __iter__(self):
        # iterate over link_id values
        return self.info_per_link_id.__iter__()
    def get_gui_data(self, link_id):
        return self[link_id].gui_data
    def set_gui_data(self, link_id, gui_data):
        self[link_id].gui_data = gui_data
        self.db.update('Link', 'link_id',
                    link_id = link_id, gui_data = gui_data)
        self.db.commit()

