from sakura.hub.mixins.bases import BaseMixin

class LinkMixin(BaseMixin):
    ENABLED = set()
    @property
    def enabled(self):
        return self.id in LinkMixin.ENABLED
    @enabled.setter
    def enabled(self, boolean):
        if boolean:
            LinkMixin.ENABLED.add(self.id)
        else:
            LinkMixin.ENABLED.discard(self.id)
    @property
    def disabled_message(self):
        if self.enabled:
            raise AttributeError
        return 'Output of source operator is not ready.'
    @property
    def dst_daemon(self):
        return self.dst_op.op_class.daemon
    @property
    def link_args(self):
        return (self.src_op.id, self.src_out_id, self.dst_op.id, self.dst_in_id)
    def pack(self):
        return dict(
            link_id = self.id,
            src_id = self.src_op.id,
            src_out_id = self.src_out_id,
            dst_id = self.dst_op.id,
            dst_in_id = self.dst_in_id,
            gui_data = self.gui_data,
            **self.pack_status_info()
        )
    def enable(self):
        self.dst_daemon.api.connect_operators(*self.link_args)
        self.enabled = True
    def disable(self):
        if self.dst_daemon.enabled:
            self.dst_daemon.api.disconnect_operators(*self.link_args)
        self.enabled = False
    @classmethod
    def create_link(cls, src_op, src_out_id, dst_op, dst_in_id):
        # create in local db
        link = cls( src_op = src_op,
                    src_out_id = src_out_id,
                    dst_op = dst_op,
                    dst_in_id = dst_in_id)
        # link remotely
        link.enable()
        return link
    def delete_link(self):
        if self.enabled:
            self.disable() # remotely
        self.delete()           # in local db
    @classmethod
    def get_possible_links(cls, src_op, dst_op):
        # list possible new links
        possible_links = dst_op.op_class.daemon.api.get_possible_links(
                                src_op.id, dst_op.id)
        # add existing links
        for l in src_op.downlinks:
            if l.dst_op.id == dst_op.id:
                possible_links += ((l.src_out_id, l.dst_in_id),)
        return possible_links
