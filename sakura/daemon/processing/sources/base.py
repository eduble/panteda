import numpy as np
from sakura.common.io import pack, ORIGIN_ID
from sakura.common.cache import Cache
from sakura.common.chunk import NumpyChunk
from sakura.common.errors import APIRequestError
from sakura.daemon.processing.column import Column, GeoColumn, BoundColumn
from sakura.daemon.csvtools import stream_csv
from time import time
from itertools import count

# We measure the total time <t> it took to compute iterator
# values, and ensure iterator is kept in cache for
# at least a delay <t>*<factor>.
CACHE_VALUE_FACTOR = 10.0
CACHE_SIZE_PER_SOURCE = 10

class ColumnsRegistry:
    def __init__(self, source):
        self.source = source
        self.ordered_columns = []
        self.uuid_to_path = {}
        self.path_to_bcol = {}
    def rebind(self, cols):
        self.ordered_columns = []
        self.uuid_to_path = {}
        self.path_to_bcol = {}
        for col in cols:
            self.append(col)
    def append(self, col):
        col_path = (len(self.ordered_columns),)
        bcol = BoundColumn(col, self.source)
        self.ordered_columns.append(bcol)
        self.uuid_to_path[col.get_uuid()] = col_path
        self.path_to_bcol[col_path] = bcol
        for col_path, bcol in self.enumerate(bcol.subcolumns, col_path, True):
            self.uuid_to_path[bcol.get_uuid()] = col_path
            self.path_to_bcol[col_path] = bcol
    def enumerate(self, columns=None, path_prefix=(), include_subcolumns=False):
        if columns is None:
            columns = self.ordered_columns
        for idx, col in enumerate(columns):
            col_path = path_prefix + (idx,)
            yield col_path, BoundColumn(col, self.source)
            if include_subcolumns:
                yield from self.enumerate(col.subcolumns, col_path, True)
    def pack(self):
        return pack(self.ordered_columns)
    def list(self, include_subcolumns=False):
        return list(col for col_path, col in \
                    self.enumerate(include_subcolumns=include_subcolumns))
    def __iter__(self):
        yield from self.ordered_columns
    def __len__(self):
        return len(self.ordered_columns)
    def __contains__(self, col):
        return col.get_uuid() in self.uuid_to_path
    def __getitem__(self, col_path):
        if isinstance(col_path, str):
            # by_uuid
            col_path = self.uuid_to_path.get(col_path)
            if col_path is None:
                raise APIRequestError('No column with this UUID in this source!')
        if isinstance(col_path, int):
            # by_integer (backward compatibility)
            col_path = (col_path,)
        # by_tuple
        bcol = self.path_to_bcol.get(col_path)
        if bcol is None:
            raise APIRequestError('No column at this index in this source!')
        return bcol
    def get_paths(self, columns, allow_subcolumns=True):
        # in order to handle subcolumns, indexes are returned as a tuple
        # (e.g. (1,0) means "2nd column > 1st subcolumn").
        paths = []
        for col in columns:
            col_uuid = col.get_uuid()
            col_path = self.uuid_to_path.get(col_uuid)
            if col_path == None:
                raise APIRequestError('Column %s not found in this source!' % col)
            if len(col_path) > 1 and not allow_subcolumns:
                raise APIRequestError('Sorry this source does not handle sub-columns.')
            paths.append(col_path)
        return tuple(paths)
    def get_path(self, column, allow_subcolumns=True):
        return self.get_paths((column,), allow_subcolumns)[0]
    def get_indexes(self, columns):
        return tuple(t[0] for t in self.get_paths(columns, False))
    def get_index(self, column):
        return self.get_indexes((column,))[0]
    def get_info(self):
        return tuple(((col_path,) + col.get_info()) \
                     for col_path, col in self.enumerate(include_subcolumns=True))

class SourceCustomData:
    def copy(self):
        c = SourceCustomData()
        for k, v in self.__dict__.items():
            setattr(c, k, v)
        return c

class SourceBase:
    num_instances = 0
    range_iter_cache = Cache(CACHE_SIZE_PER_SOURCE)
    def __init__(self, label):
        # all columns
        self.all_columns = ColumnsRegistry(self)
        # selected columns
        self.columns = ColumnsRegistry(self)
        # row filters
        self.row_filters = ()
        # other attributes
        self.label = label
        self.length = None
        self.origin_id = ORIGIN_ID
        SourceBase.num_instances += 1
        SourceBase.range_iter_cache.resize(
                   SourceBase.num_instances * CACHE_SIZE_PER_SOURCE)
        self.data = SourceCustomData()
    def __del__(self):
        SourceBase.num_instances -= 1
    def add_column(self, col_label, col_type, col_tags=(), **col_type_params):
        existing_col_names = set(col._label for col in self.all_columns.list(True))
        # avoid having twice the same column name
        if col_label in existing_col_names:
            for i in count(start=2):
                alt_label = '%s(%d)' % (col_label, i)
                if alt_label not in existing_col_names:
                    col_label = alt_label
                    break
        if col_type == 'geometry':
            col_class = GeoColumn
        else:
            col_class = Column
        col = col_class(col_label, col_type, tuple(col_tags), **col_type_params)
        self.all_columns.append(col)
        self.columns.append(col)
        return col
    def pack(self):
        return pack(dict(label = self.label,
                    columns = self.columns,
                    length = self.length))
    def get_origin_id(self):
        return self.origin_id
    def get_label(self):
        return self.label
    def get_length(self):
        return self.length
    def get_columns_info(self):
        return self.columns.get_info()
    def get_range(self, row_start, row_end):
        startup_time = time()
        chunk_len = row_end-row_start
        # try to reuse the last iterator
        cache_key=(id(self), row_start, row_end)
        it, compute_time = SourceBase.range_iter_cache.pop(cache_key, default=(None, None))
        in_cache = it is not None
        # otherwise, create a new iterator
        if not in_cache:
            it = self.chunks(chunk_len, row_start)
            compute_time = 0
        # read next chunk and return it
        for chunk in it:
            # having chunk.size < chunk_len would mean we are at the end
            # of the iterator. let's check that's not the case.
            if chunk.size == chunk_len:
                # update cache for later reuse of this iterator.
                new_row_start = row_start + chunk.size
                compute_time += time()- startup_time
                expiry_delay = compute_time * CACHE_VALUE_FACTOR
                cache_key = (id(self), new_row_start, new_row_start + chunk_len)
                cache_item = (it, compute_time)
                SourceBase.range_iter_cache.save(cache_key, cache_item, expiry_delay)
            return chunk
        # if we are here, stream has ended, return empty chunk
        return NumpyChunk.empty(self.get_dtype())
    def get_dtype(self):
        return np.dtype(list(bcol.get_dtype() for bcol in self.columns))
    # deprecated (use select() instead)
    def select_columns(self, *col_indexes):
        # verify that at least 1 column is specified
        if len(col_indexes) == 0:
            return self
        col_indexes = tuple(col_indexes)
        # compute a substream
        columns = tuple(self.columns[idx] for idx in col_indexes)
        return self.select(*columns)
    # deprecated (use where() instead)
    def filter_column(self, col_index, comp_op, other):
        return self.filtered(self.columns[col_index], comp_op, other)
    def stream_csv(self, gzip_compression=False):
        header_labels = tuple(col._label for col in self.columns)
        stream = self.chunks()
        yield from stream_csv(
                    header_labels, stream, gzip_compression)
    def filtered(self, col, comp_op, other):
        new_row_filters = self.row_filters + ((col, comp_op, other),)
        return self.reinstanciate(row_filters=new_row_filters)
    def reinstanciate(self, columns = None, row_filters = None):
        source = self.__class__(self.label)
        # self.all_columns always remains the same
        source.all_columns.rebind(self.all_columns)
        # selected columns may change
        if columns is None:
            columns = self.columns  # if unchanged
        source.columns.rebind(columns)
        # row_filters may change
        if row_filters is None:
            row_filters = self.row_filters  # if unchanged
        source.row_filters = tuple(row_filters)
        # transmit custom data
        source.data = self.copy_data()
        return source
    def copy_data(self):
        return self.data.copy()
    def select(self, *columns):
        return self.reinstanciate(columns = columns)
    def where(self, col_filter):
        return col_filter.filtered_sources(self)[0]
    def __iter__(self):
        for chunk in self.chunks():
            yield from chunk
