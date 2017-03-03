class GuiToHubAPI(object):
    def __init__(self, context):
        self.context = context
    
    ########################################
    # Daemons
    def list_daemons(self):
        return list(self.context.list_daemons_serializable())
    
    
    ########################################
    # Operators
    
    def list_operators_classes(self):
        return self.context.list_op_classes_serializable()
    
    def list_operators_instance_ids(self):      // TODO
        return self.context.list_op_instance_ids()
    
    # instantiate an operator and return the instance info
    def create_operator_instance(self, cls_id):
        return self.context.create_operator_instance(cls_id)
    
    # delete operator instance and links involved
    def delete_operator_instance(self, op_id):
        return self.context.delete_operator_instance(op_id)
    
    # returns info about operator instance: cls_name, inputs, outputs, parameters
    def get_operator_instance_info(self, op_id):
        return self.context.op_instances[op_id].get_info_serializable()
    
    def set_parameter_value(self, op_id, param_id, value):
        return self.context.op_instances[op_id].parameters[param_id].set_value(value)
    
    def get_operator_input_range(self, op_id, in_id, row_start, row_end):
        return self.context.op_instances[op_id].input_streams[in_id].get_range(row_start, row_end)
    
    def get_operator_output_range(self, op_id, out_id, row_start, row_end):
        return self.context.op_instances[op_id].output_streams[out_id].get_range(row_start, row_end)
    
    def get_operator_internal_range(self, op_id, intern_id, row_start, row_end):
        return self.context.op_instances[op_id].internal_streams[intern_id].get_range(row_start, row_end)
    
    def get_operator_file_content(self, op_id, file_path):
        return self.context.op_instances[op_id].get_file_content(file_path)
        
    def fire_operator_event(self, op_id, event):
        return self.context.op_instances[op_id].handle_event(event)
    
    
    ########################################
    # Links
    def list_link_ids(self):      // TODO
        return self.context.list_link_ids()
    
    def get_link_info(self, link_id):      // TODO
        return self.context.get_link_info(link_id)
    
    def create_link(self, src_op_id, src_out_id, dst_op_id, dst_in_id):
        return self.context.create_link(src_op_id, src_out_id, dst_op_id, dst_in_id)
    
    def delete_link(self, link_id):
        return self.context.delete_link(link_id)
    
    
    ########################################
    # Gui
    def set_operator_instance_gui_data(self, op_id, gui_data):      # TODO
        return self.context.op_instances[op_id].set_gui_data(gui_data)
    
    def get_operator_instance_gui_data(self, op_id):      # TODO
        return self.context.op_instances[op_id].get_gui_data()
    
    def set_project_gui_data(self, project_gui_data):      # TODO
        return self.context.set_project(project_gui_data)
    
    def get_project_gui_data(self):      # TODO
        return self.context.get_project_gui_data()
