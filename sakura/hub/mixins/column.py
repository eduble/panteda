class ColumnMixin:
    def pack(self):
        # TODO: we should not expose daemon tags here, they
        # should only be used for the processing on the daemon side.
        # on the daemon side, the abstract type (e.g. timestamp, etc.)
        # should be returned when probing, instead of native db type + tags.
        tags = tuple(set(self.daemon_tags) | set(self.user_tags)) # union
        return self.col_name, self.col_type, tags
    def pack_for_daemon(self):
        return self.col_name, self.col_type
    @classmethod
    def create_or_update(cls, table, col_name, **kwargs):
        column = cls.get(table = table, col_name = col_name)
        if column is None:
            column = cls(table = table, col_name = col_name, **kwargs)
        else:
            column.set(**kwargs)
        return column
    @classmethod
    def restore_column(cls, context, table, col_name, col_type, daemon_tags):
        return cls.create_or_update(table, col_name,
                                    col_type = col_type,
                                    daemon_tags = daemon_tags)
    @classmethod
    def create_column(cls, context, table, col_name, col_type, user_tags):
        return cls.create_or_update(table, col_name,
                                    col_type = col_type,
                                    user_tags = user_tags)