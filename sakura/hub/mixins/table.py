import time
from sakura.common.tools import greenlet_env

class TableMixin:
    def pack(self):
        return dict(
            table_id = self.id,
            database_id = self.database.id,
            name = self.name,
            short_desc = self.short_desc,
            creation_date = self.creation_date,
            columns = tuple(c.pack() for c in self.columns)
        )
    def create_on_datastore(self):
        greenlet_env.user = 'etienne'               # TODO: handle this properly
        greenlet_env.password = 'sakura_etienne'    # TODO: handle this properly
        database = self.database
        datastore = database.datastore
        datastore.daemon.api.create_table(
                greenlet_env.user,
                greenlet_env.password,
                datastore.host,
                datastore.driver_label,
                database.name,
                self.name,
                tuple(c.pack_for_daemon() for c in self.columns))
    @classmethod
    def create_or_update(cls, database, name, **kwargs):
        table = cls.get(database = database, name = name)
        if table is None:
            table = cls(database = database, name = name, **kwargs)
        else:
            table.set(**kwargs)
        return table
    @classmethod
    def restore_table(cls, context, database, columns, **tbl):
        table = cls.create_or_update(database, **tbl)
        table.columns = set(context.columns.restore_column(context, table, *col) for col in columns)
        return table
    @classmethod
    def create_table(cls, context, database, name, columns,
                            creation_date = None, **kwargs):
        if creation_date is None:
            creation_date = time.time()
        # register in central db
        new_table = cls(database = database,
                        name = name,
                        creation_date = creation_date)
        cols = []
        for col_info in columns:
            col = context.columns.create_column(context, new_table, *col_info)
            cols.append(col)
        new_table.set(columns = cols, **kwargs)
        # request daemon to create table on the remote datastore
        new_table.create_on_datastore()
        # return table_id
        context.db.commit()
        return new_table.id

