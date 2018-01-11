import numpy as np

class DBColumn:
    def __init__(self,  table_name,
                        col_name,
                        np_type,
                        col_name_wrapper,
                        value_wrapper,
                        tags,
                        primary_key,
                        foreign_key_info):
        self.table_name = table_name
        self.col_name = col_name
        self.np_dtype = np.dtype(np_type)
        self.col_name_wrapper = col_name_wrapper
        self.value_wrapper = value_wrapper
        self.tags = list(tags)
        self.primary_key = primary_key
        self.foreign_key_info = foreign_key_info
    def pack(self):
        return (self.col_name, str(self.np_dtype), self.tags,
                        self.primary_key, self.foreign_key_info)
    def to_sql(self):
        return self.col_name_wrapper % dict(
            table_name = self.table_name,
            col_name = self.col_name
        )

