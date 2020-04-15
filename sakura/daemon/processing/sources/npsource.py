import numpy as np
from sakura.daemon.processing.sources.base import SourceBase
from sakura.common.chunk import NumpyChunk
from sakura.common.types import np_dtype_to_sakura_type

DEFAULT_CHUNK_SIZE = 100000

class NumpyArraySource(SourceBase):
    def __init__(self, label, array = None):
        SourceBase.__init__(self, label)
        if array is not None:
            self.data.array = array
            for col_label in array.dtype.names:
                col_dt = array.dtype[col_label]
                col_type, col_type_params = np_dtype_to_sakura_type(col_dt)
                self.add_column(col_label, col_type, **col_type_params)
    def chunks(self, chunk_size = DEFAULT_CHUNK_SIZE, offset=0):
        col_indexes = self.all_columns.get_indexes(self.columns)
        array = self.data.array.view(NumpyChunk).__select_columns_indexes__(col_indexes)
        if len(self.row_filters) == 0:
            # iterate over all rows
            while offset < array.size:
                yield array[offset:offset+chunk_size].view(NumpyChunk)
                offset += chunk_size
        else:
            # select appropriate row indices
            row_indices = None  # all indices for now
            for col, comp_op, other in self.row_filters:
                array_col = array[col._label]
                if row_indices is not None:
                    array_col = array_col[row_indices]  # keep only the indices that passed prev filters
                # with numpy, the result of an expression like
                # <array> > 20
                # is a table of booleans indicating whether or not each row
                # satisfies the condition.
                booleans = comp_op(array_col, other)
                # applying nonzero()[0] gives the position where the booleans are True
                new_indices = booleans.nonzero()[0]
                # translate back the new indices in original numbering
                if row_indices is None:
                    row_indices = new_indices
                else:
                    row_indices = row_indices[new_indices]
            while offset < row_indices.size:
                yield array[row_indices[offset:offset+chunk_size]].view(NumpyChunk)
                offset += chunk_size
