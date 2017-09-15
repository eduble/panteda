//Code started by Michael Ortega for the LIG
//August, 22nd, 2017


var global_ids = 0;
var file_lines = null;

function not_yet() {
    alert("not yet implemented");
}


function recover_datasets() {
    
    var database_id = window.location.search.substr(1).split("=")[1];
    //console.log(parseInt(database_id));
    database_id = 3;
    sakura.common.ws_request('get_database_info', [parseInt(database_id)], {}, function (result) {
        
        console.log(result);
        //Filling dataset
        var body = $('#table_of_datasets').find('tbody');
        body.empty();
        result['tables'].forEach( function(dataset) {
            console.log(dataset);
            body.append('<tr>   <td>'+dataset['name']+'</td><td>'+dataset['short_description']+'</td> \
                                <td align="right"> \
                                    <span title="Upload data in this dataset" class="glyphicon glyphicon-upload" style="cursor: pointer;" onclick="dataset_upload('+database_id+','+dataset['id']+');"> </span> \
                                    <span title="Download the dataset" class="glyphicon glyphicon-download" style="cursor: pointer;" onclick="dataset_download('+database_id+','+dataset['id']+');"> </span> \
                                    <span>&nbsp</span> \
                                    <span title="Look at the dataset" class="glyphicon glyphicon-eye-open" style="cursor: pointer;" onclick="dataset_look_at('+database_id+','+dataset['id']+');"></span> \
                                    <span title="Analytics" class="glyphicon glyphicon-info-sign" style="cursor: pointer;" onclick="dataset_analytics('+database_id+','+dataset['id']+');"></span> \
                                    <span>&nbsp</span> \
                                    <span title="delete" class="glyphicon glyphicon-remove" style="cursor: pointer;" onclick="dataset_delete('+database_id+','+dataset['id']+');"></span> \
                                </td>\
                        </tr>');
        });
        
        //Updating/emptying html elements
        
        $('#datasets_creation_name').val("");
        $('#datasets_creation_description').val("");
        $("#datasets_file_from_HD").val("");
        $('#datasets_creation_button').attr('onclick', 'datasets_send_new('+database_id+')');
        
        datasets_add_a_row('datasets_creation_from_scratch_columns');
        
    });
}


function datasets_send_new(database_id) {
    $("#datasets_creation_modal").modal('hide');
    //var dataset_def = []
    
    var body = $('#datasets_creation_from_scratch_columns').find('tbody');
    var nb_cols = body.find('tr').length - 1;
    $('#datasets_creation_from_file_pan').attr("class").split(' ').forEach( function (elt) {
        if (elt == 'active') {
            body = $('#datasets_creation_from_file_columns').find('tbody');
            nb_cols = body.find('tr').length
        }
    });
    console.log(nb_cols);
    //console.log("Params", dataset_def);
}


function dataset_upload(database_id, dataset_id) {
    not_yet();
}


function dataset_download(database_id, dataset_id) {
    not_yet();
}

function dataset_look_at(database_id, dataset_id) {
    not_yet();
}


function dataset_analytics(database_id, dataset_id) {
    not_yet();
}


function dataset_delete(database_id, dataset_id) {
    not_yet();
}


function on_file_selected(f) {
    var fr = new FileReader();
    
    fr.onload = function(e) {
        //check the name: should have .csv extension
        
        var s_name = f.value.split('.');
        if (s_name[s_name.length - 1] != 'csv' && s_name[s_name.length - 1] != 'CSV') {
            console.log(s_name[s_name.length - 1]);
            alert("The extension of this file is not .csv !! Please be sure it is a csv file, and rename it with extension.");
            return;
        }
        file_lines = e.target.result.split(/[\r\n]+/g);
        
        //ask for the separator
        $('#datasets_csv_separator_modal').modal();
    };
    
    fr.readAsText(f.files[0]);
}


function datasets_parse_file() {
    
    //read separator
    var sep = $('#datasets_csv_separator')[0].value;
    
    //check the columns and the first line (dealing with comments)
    var index  = 0
    var cols =['#'];    
    while (cols[0].indexOf('#') >= 0) {
        cols = file_lines[index].split(sep);
        index ++;
    }
    var first_line = ['#'];
    while (first_line[0].indexOf('#') >= 0) {
        first_line = file_lines[index].split(sep);
        index ++;
    }
    
    var body = $('#datasets_creation_from_file_columns').find('tbody');
    body.empty();
    cols.forEach( function(col, index) {
        var new_row = $(body[0].insertRow(-1));
        new_row.load('creation_dataset_row.html', function () {
            var inputs = new_row.find('input');
            var buttons = new_row.find('button');
            var select = new_row.find('select');
            inputs[0].value = col;
            
            buttons[buttons.length - 1].remove();
            
            select.val(getType(first_line[index]));
        });
    });
}


function datasets_add_a_row(dataset_id) {
    var body = $('#'+dataset_id).find('tbody');
    var nb_rows = body[0].childElementCount - 1;
    var new_row = $(body[0].insertRow(nb_rows));
    new_row.attr('id', 'datasets_row_' + global_ids);
    
    new_row.load('creation_dataset_row.html', function () {
        var last_cel = $(new_row[0].childNodes[new_row[0].childNodes.length - 1]);
        $(last_cel.find('button')[0]).attr('onclick', 'datasets_delete_row('+global_ids+');');
        global_ids ++;
    });    
    
    return new_row;
}


function datasets_delete_row(row_id) {
    $('#datasets_row_'+row_id).remove();
}


function getType(str){
    if (typeof str !== 'string') str = str.toString();
    var nan = isNaN(Number(str));
    var isfloat = /^\d*(\.|,)\d*$/;
    var commaFloat = /^(\d{0,3}(,)?)+\.\d*$/;
    var dotFloat = /^(\d{0,3}(\.)?)+,\d*$/;
    var date = /^\d{0,4}(\.|\/)\d{0,4}(\.|\/)\d{0,4}$/;
    var email = /^[A-za-z0-9._-]*@[A-za-z0-9_-]*\.[A-Za-z0-9.]*$/;
    var phone = /^\+\d{2}\/\d{4}\/\d{6}$/g;
    if (!nan){
        if (parseFloat(str) === parseInt(str)) return "integer";
        else return "float";
    }
    else if (isfloat.test(str) || commaFloat.test(str) || dotFloat.test(str)) return "float";
    else if (date.test(str)) return "date";
    else {
        if (email.test(str)) return "e-mail";
        else if (phone.test(str)) return "phone";
        else return "string";
    }
}