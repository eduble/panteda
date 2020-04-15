from sakura.common.chunk import NumpyChunk
from sakura.daemon.processing.sources.base import SourceBase
from sakura.common.ops import LOWER, LOWER_OR_EQUAL, GREATER, GREATER_OR_EQUAL, IN, EQUALS, NOT_EQUALS
from sakura.daemon.processing.geo import GeoBoundingBox

COMP_OP_TO_SQL_SPECIAL = {
    (EQUALS, None):     'IS NULL',
    (NOT_EQUALS, None): 'IS NOT NULL'
}

COMP_OP_TO_SQL = {
    LOWER:              '<',
    LOWER_OR_EQUAL:     '<=',
    EQUALS:             '=',
    NOT_EQUALS:         '!=',
    GREATER:            '>',
    GREATER_OR_EQUAL:   '>='
}

#PRINT_SQL=False
PRINT_SQL=True

class SQLSourceIterator:
    def __init__(self, source, chunk_size, offset):
        self.chunk_size = chunk_size
        self.dtype = source.get_dtype()
        self.db_conn = source.data.db.connect()
        self.cursor = source.open_cursor(self.db_conn, offset)
        if self.chunk_size == None:
            self.chunk_size = self.cursor.arraysize
    @property
    def released(self):
        return self.db_conn is None and self.cursor is None
    def __iter__(self):
        return self
    def __next__(self):
        if self.released:
            raise StopIteration
        chunk_data = self.cursor.fetchmany(self.chunk_size)
        if len(chunk_data) < self.chunk_size:
            # less data than expected => end of stream
            self.release()
        if len(chunk_data) == 0:
            raise StopIteration
        return NumpyChunk.create(chunk_data, self.dtype)
    def release(self):
        if self.cursor is not None:
            self.cursor.close()
            self.cursor = None
        if self.db_conn is not None:
            self.db_conn.close()
            self.db_conn = None
    def __del__(self):
        self.release()

class SQLDatabaseSource(SourceBase):
    def __init__(self, label, db = None, db_columns = None):
        SourceBase.__init__(self, label)
        if db_columns is not None:
            self.data.db = db
            # auto populate source columns
            for db_col in db_columns:
                col = self.add_column(db_col.col_name, db_col.col_type, db_col.tags,
                                      **db_col.col_type_params)
                # link db_col in each generic source column object
                col.data.db_col = db_col
                for subcol, db_subcol in zip(col.subcolumns, db_col.subcolumns):
                    subcol.data.db_col = db_subcol
    def chunks(self, chunk_size = None, offset=0):
        return SQLSourceIterator(self, chunk_size, offset)
    def open_cursor(self, db_conn, offset=0):
        sql_text, values = self.to_sql(offset)
        if PRINT_SQL:
            print(sql_text, values)
        cursor = self.data.db.dbms.driver.open_server_cursor(db_conn)
        cursor.execute(sql_text, values)
        return cursor
    def merge_in_bbox_row_filters(self, db_row_filters):
        bbox_per_column = {}
        other_row_filters = []
        for db_row_filter in db_row_filters:
            db_column, comp_op, value = db_row_filter
            if comp_op is IN:
                bbox = bbox_per_column.get(db_column)
                if bbox is None:
                    bbox = value
                else:
                    bbox = bbox.intersect(value)
                bbox_per_column[db_column] = bbox
            else:
                other_row_filters.append(db_row_filter)
        bbox_row_filters = ((db_column, IN, bbox) for db_column, bbox in bbox_per_column.items())
        return tuple(other_row_filters) + tuple(bbox_row_filters)
    def to_sql(self, offset):
        selected_db_cols = tuple(col.data.db_col for col in self.columns)
        db_row_filters = tuple((col.data.db_col, comp_op, other) for col, comp_op, other in self.row_filters)
        db_row_filters = self.merge_in_bbox_row_filters(db_row_filters)
        select_clause = 'SELECT ' + ', '.join(db_col.to_sql_select_clause() for db_col in selected_db_cols)
        tables = set(db_col.table.name for db_col in selected_db_cols)
        tables |= set(f[0].table.name for f in db_row_filters)
        from_clause = 'FROM "' + '", "'.join(tables) + '"'
        where_clause, offset_clause, filter_vals = '', '', ()
        if len(db_row_filters) > 0:
            filter_texts, filter_vals = (), ()
            for db_row_filter in db_row_filters:
                filter_info = self.db_row_filter_to_sql(db_row_filter)
                filter_texts += filter_info[0]
                filter_vals += filter_info[1]
            where_clause = 'WHERE ' + ' AND '.join(filter_texts)
        if offset > 0:
            offset_clause = "OFFSET " + str(offset)
        sql_text = ' '.join((select_clause, from_clause, where_clause, offset_clause))
        return (sql_text, filter_vals)
    def db_row_filter_to_sql(self, db_row_filter):
        db_column, comp_op, value = db_row_filter
        col_name = db_column.to_sql_where_clause()
        op_sql_special = COMP_OP_TO_SQL_SPECIAL.get((comp_op, value), None)
        if op_sql_special != None:
            sql = col_name + ' ' + op_sql_special
            return (sql,), ()
        if comp_op is IN and isinstance(value, GeoBoundingBox):
            sql = 'ST_Contains(' + db_column.value_wrapper + ', ' + col_name + ')'
            value = value.as_geojson()
        else:
            op_sql = COMP_OP_TO_SQL.get(comp_op, None)
            if op_sql is None:
                op_sql = getattr(comp_op, 'SQL_OP', None)
            assert op_sql != None, ("Don't know how to write %s as an SQL operator." % str(comp_op))
            sql = col_name + ' ' + op_sql + ' ' + db_column.value_wrapper
        return (sql,), (value,)


class SQLTableSource(SQLDatabaseSource):
    def __init__(self, label, db_table = None):
        if db_table is not None:
            SQLDatabaseSource.__init__(self, label, db_table.db, db_table.columns)
        else:
            SQLDatabaseSource.__init__(self, label)
