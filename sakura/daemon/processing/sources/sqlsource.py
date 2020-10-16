import numpy as np
from sakura.common.chunk import NumpyChunk
from sakura.common.exactness import EXACT
from sakura.common.stream import reassemble_chunk_stream
from sakura.daemon.processing.sources.base import SourceBase
from sakura.common.ops import LOWER, LOWER_OR_EQUAL, GREATER, GREATER_OR_EQUAL, IN, EQUALS, NOT_EQUALS
from sakura.daemon.processing.geo import GeoBoundingBox
from sakura.daemon.processing.sort.tools import get_cut_position
from sakura.daemon.db import CURSOR_MODE

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
DEBUG=False

class SQLSourceIterator:
    def __init__(self, db_conn, source, chunk_size):
        self.db_conn = db_conn
        self.chunk_size = chunk_size
        self.dtype = source.get_dtype()
        self.cursor = source.open_cursor(self.db_conn)
        if self.chunk_size == None:
            self.chunk_size = self.cursor.arraysize
    @property
    def released(self):
        return self.cursor is None
    def __iter__(self):
        return self
    def __next__(self):
        if self.released:
            raise StopIteration
        chunk_data = self.cursor.fetchmany(self.chunk_size)
        if len(chunk_data) < self.chunk_size:
            # less data than expected => end of stream
            if DEBUG:
                print('SQLSourceIterator: releasing cursor', self.cursor, 'at', self.db_conn)
            self.cursor.close()
            self.cursor = None
        if len(chunk_data) == 0:
            raise StopIteration
        return NumpyChunk.create(chunk_data, self.dtype, EXACT)

# let's consider this query:
# select * from t1, t2 where t1.a = t2.a order by t2.b
# (and we have indexes on t1.a, t2.a and t2.b)

# in many cases database engines generate this obvious query plan:
# join(t1.a,t2.a), then sort on t2.b

# the problem with this query plan, is that streaming output rows can
# only start at the end of the query plan execution (after the sort()).

# another possible query plan is the following:
# sort on t2.b, then
# for each output row r look for rows in t1 where t1.a = r.a,
# and output these joint rows.

# this query plan allows to start streaming rows very soon.
# but this query plan is not often selected because computing the whole
# resultset this way is slower than with the other query plan.

# some database systems propose a parameter allowing to skew the query
# engine towards quickly getting the first rows (e.g. cursor_tuple_fraction
# in postgresql).

# we propose here a more adaptive and portable method: we use LIMIT and
# OFFSET directives in order to split the query into several subqueries.
# The first subquery is limited to a small number of rows thanks to a
# small LIMIT value, thus the database engine should optimize it appropriately
# (choosing the second type of query plan in our example above) and return
# these first rows shortly. If the client consumes all returned rows,
# we issue a second query with appropriate OFFSET in order to avoid returning
# twice the same rows, and a greater LIMIT. And so on.

# we have one remaining problem. if the case of equal values on the sort columns,
# there is a risk that two consecutive subqueries may not order them the same
# way (especiallly if they were executed using a different query plan), thus the
# LIMIT and OFFSET trick may return duplicated rows and miss some of them.

# thus we have to compute the LIMIT/OFFSET frontier appropriately: the last
# row of a subquery and the first row of the next one should have different
# values on the sort columns.

class SQLSourceSkewedIterator:
    def __init__(self, source, chunk_size):
        self.source = source
        self.chunk_size = chunk_size
        self._final_iter = None
    def __iter__(self):
        return self
    def __next__(self):
        if self._final_iter is None:
            it = self._skewed_iterator()
            self._final_iter = reassemble_chunk_stream(it, self.source.get_dtype(), self.chunk_size)
        return next(self._final_iter)
    def _skewed_iterator(self):
        # we will work on work_source where selected columns are
        # self.source.sort_columns + self.source.columns
        # this allows us to:
        # - ensure sort_columns are selected (it may not be the case...)
        # - for a given chunk:
        #   - quickly check the values of the sort_columns
        #   - quickly retrieve values of self.source.columns
        work_columns = list(self.source.sort_columns) + list(self.source.columns)
        work_source = self.source.select(*work_columns)
        sort_col_indexes = np.arange(len(self.source.sort_columns))
        other_col_indexes = np.arange(len(self.source.columns)) + sort_col_indexes.size
        held_chunks = []
        curr_sort_columns = None
        emitted_offset = self.source._offset
        offset = self.source._offset
        limit = 1000
        db_conn = None
        while True:
            db_conn = self.source.connect(reuse_conn = db_conn)
            source = work_source.offset(offset).limit(limit)
            if DEBUG:
                print('QUERY OFFSET', offset, 'LIMIT', limit)
            it = SQLSourceIterator(db_conn, source, self.chunk_size)
            for chunk in it:
                sort_cols_chunk = chunk[:,sort_col_indexes]
                other_cols_chunk = chunk[:,other_col_indexes]
                # if for all rows of new chunk sort columns equal the previous value,
                # hold it as a whole (we check the last value only, since the chunk is ordered...)
                if curr_sort_columns is not None and sort_cols_chunk[-1] == curr_sort_columns:
                    held_chunks.append(other_cols_chunk)
                    continue
                # flush held chunks
                for chunk in held_chunks:
                    emitted_offset += chunk.size
                    yield chunk
                held_chunks = []
                # check where we can cut new chunk
                cut_pos = get_cut_position(sort_cols_chunk)
                if cut_pos == 0:
                    held_chunks.append(other_cols_chunk)
                else:
                    emitted_offset += cut_pos
                    yield other_cols_chunk[:cut_pos]
                    held_chunks.append(other_cols_chunk[cut_pos:])
                curr_sort_columns = sort_cols_chunk[-1]
            # query iterator ended
            held_count = sum(chunk.size for chunk in held_chunks)
            if emitted_offset + held_count < offset + limit:
                # the query returned less results than its <limit> parameter
                # => we are at the end of the result stream
                yield from held_chunks
                break
            else:
                # the query returned <limit> rows, continue with another one
                limit *= 10
                offset = emitted_offset
                held_chunks = []
                continue

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
    def connect(self, reuse_conn = None):
        return self.data.db.connect(cursor_mode = CURSOR_MODE.SERVER,
                                    reuse_conn = reuse_conn)
    def all_chunks(self, chunk_size = None):
        if self._limit is None:
            # We want to apply our method to skew the database engine towards quickly getting the
            # first rows (see long comment above).
            # If no sort is applied, we cannot apply the same, because the requests
            # we would send could return data with a different ordering, so LIMIT
            # and OFFSET keywords are not enough to ensure stream integrity.
            if len(self.sort_columns) > 0:
                return SQLSourceSkewedIterator(self, chunk_size)
            # The user did not request a sorted result, but selecting one would still be a valid
            # response. Let's check if there is a primary key somewhere, which would prove
            # we have an index. Sorting on a primary key will probably not hurt performance much.
            for db_table in set(col.data.db_col.table for col in self.all_columns):
                db_primary_key = db_table.primary_key
                if len(db_primary_key) > 0:
                    # yes we have a primary key!
                    # let's convert its db col names to source columns
                    primary_key = []
                    for db_col_name in db_primary_key:
                        for col in self.all_columns:
                            if col.data.db_col.table == db_table and \
                                    col.data.db_col.col_name == db_col_name:
                                primary_key.append(col)
                                break
                    # add our selected ordering and apply our skewed algorithm.
                    source = self.sort(*primary_key)
                    return SQLSourceSkewedIterator(source, chunk_size)
        # if the query already has a LIMIT, or as a last resort,
        # iterate in a standard way
        return SQLSourceIterator(self.connect(), self, chunk_size)
    def open_cursor(self, db_conn):
        sql_text, values = self.to_sql()
        if PRINT_SQL:
            print(sql_text, values)
        cursor = db_conn.execute(sql_text, values)
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
    def to_sql(self):
        selected_db_cols = tuple(col.data.db_col for col in self.columns)
        db_row_filters = tuple((col.data.db_col, comp_op, other) for col, comp_op, other in self.row_filters)
        db_row_filters = self.merge_in_bbox_row_filters(db_row_filters)
        db_join_conds = tuple((left_col.data.db_col, right_col.data.db_col) for left_col, right_col in self.join_conds)
        select_clause = 'SELECT ' + ', '.join(db_col.to_sql_select_clause() for db_col in selected_db_cols)
        tables = set(db_col.table.name for db_col in selected_db_cols)
        tables |= set(f[0].table.name for f in db_row_filters)
        from_clause = 'FROM "' + '", "'.join(tables) + '"'
        where_clause, sort_clause, offset_clause, limit_clause, filter_vals = '', '', '', '', ()
        cond_texts, cond_vals = (), ()
        for db_row_filter in db_row_filters:
            cond_info = self.db_row_filter_to_sql(db_row_filter)
            cond_texts += cond_info[0]
            cond_vals += cond_info[1]
        cond_texts += tuple(self.db_join_cond_to_sql(db_join_cond) for db_join_cond in db_join_conds)
        if len(cond_texts) > 0:
            where_clause = 'WHERE ' + ' AND '.join(cond_texts)
        if len(self.sort_columns) > 0:
            sort_db_cols = tuple(col.data.db_col for col in self.sort_columns)
            sort_clause = "ORDER BY " + ', '.join(db_col.to_sql_sort_clause() for db_col in sort_db_cols)
        if self._offset > 0:
            offset_clause = "OFFSET " + str(self._offset)
        if self._limit is not None:
            limit_clause = "LIMIT " + str(self._limit)
        sql_text = ' '.join((select_clause, from_clause, where_clause, sort_clause, offset_clause, limit_clause))
        return (sql_text, cond_vals)
    def db_join_cond_to_sql(self, db_join_cond):
        db_left_col, db_right_col = db_join_cond
        return db_left_col.to_sql_where_clause() + ' = ' + db_right_col.to_sql_where_clause()
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
    def get_native_join_id(self):
        return ('SQLDatabaseSource', self.data.db.unique_id())

class SQLTableSource:
    def __new__(cls, label, db_table = None):
        if db_table is not None:
            return SQLDatabaseSource(label, db_table.db, db_table.columns)
        else:
            return SQLDatabaseSource(label)
