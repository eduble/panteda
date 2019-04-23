var ws = new WebSocket("ws://localhost:10433");
var recover = false;
var last_date = new Date();
var canvas = document.getElementById("myCanvas");
var wiggle_status = false;

function init_server() {
    ws.onopen = function(event) {
        console.log('Connection: open');
        send('get_trajectories');
    }
    ws.onclose = function(event) {
        console.log('Connection closed');
    }
    ws.onmessage = function(event) {
        if (event.data instanceof Blob) {
            var image = new Image();
            image.src = URL.createObjectURL(event.data);

            image.onload = function() {
                var ctx = canvas.getContext("2d");
                ctx.drawImage(image,0,0);
                ctx.restore();

                if (recover) {
                    //var new_date = new Date();
                    //console.log(1000/(new_date - last_date));
                    //last_date = new_date;
                    //send('image');
                }
            }
        }
        else {
            var j = JSON.parse(event.data);
            if (j.key == 'resize') {
                recover = true;
            }
            else if (j.key == 'data_directories') {
                var dirs = JSON.parse(j.value);
                for (var i in dirs) {
                  var select = document.getElementById("directories_select");
                  var option = document.createElement("option");
                  option.text = dirs[i];
                  option.value = i;
                  select.add(option);
                }
            }
            else if (j.key == 'get_trajectories') {
                fill_trajectories_db(j.value);
            }
            else if (j.key == 'darkness') {
                send('image');
            }
            else if (['move',
                      'click',
                      'wheel',
                      'hide_trajectories',
                      'show_trajectories'].indexOf(j.key) < 0) {
                console.log('Unknown answer:', j);
            }
        }
        return;
    }

    setInterval(function(){send('image');}, 50);
}

function fill_trajectories_db(trajs) {
    nb_trajectories = trajs.length;
    var tdd = $('#trajectories_dropdown');
    var butt_hid = $('<button class="btn btn-default btn-xs" onclick=\'check_trajectory(-1);\'>hide all</button>&nbsp;');
    var butt_sho = $('<button class="btn btn-default btn-xs" onclick=\'check_trajectory(-2);\'>show all</button>');
    butt_hid.innerHTML = 'hide all';
    var table = $('<table width = 100%>');

    trajs.forEach( function(traj, index) {
        table.append("<tr><td><input type='checkbox' checked id='traj_checkbox_"+index+"' onclick='check_trajectory("+index+");'></td><td>"+traj+"</td></tr>");
    });

    tdd.append(butt_hid);
    tdd.append(butt_sho);
    tdd.append(table);
}
function check_trajectory(index) {
    var l = [index];
    var func = "hide_trajectories"

    //only one trajectory
    if (index != -1 && index != -2) {
        if ($('#traj_checkbox_'+index).is(":checked"))
            func = "show_trajectories"
    }
    //all trajectories
    else {
        var val = false;
        if (index == -2) {
            val = true;
            func = "show_trajectories";
        }
        l = []
        for (var i=0; i< nb_trajectories;i++) {
              $('#traj_checkbox_'+i).each(function(){ this.checked = val; });
              l.push(i);
        }
    }
    send(func, [l]);
}

function send(key, data) {
    var message = { "key": key, 'data': data};
    ws.send(JSON.stringify(message));
}

function getMousePos(canvas, evt) {
    var rect = canvas.getBoundingClientRect();
    return {
        x: parseInt(evt.clientX - rect.left),
        y: parseInt(evt.clientY - rect.top)
    };
}

function wiggle() {
    wiggle_status = !wiggle_status;
    send('wiggle', [wiggle_status]);
}

function tile_type() {
    select = document.getElementById('tile_type_select');
    send('tile', [select.options[select.selectedIndex].value]);
}

function floor_darkness() {
    var val = document.getElementById('darkness_range').value/100;
    send('darkness', [val]);
}

function select_dir() {
    var select = document.getElementById("directories_select");
    send('data_directory', [select.options[select.selectedIndex].text])
    darkness();
}
canvas.addEventListener('mousemove', function(evt) {
    var pos = getMousePos(canvas, evt);
    send('move', [pos.x, pos.y]);
}, false);

canvas.addEventListener('mousedown', function(evt) {
    evt.preventDefault();
    var button = 'right';
    var pos = getMousePos(canvas, evt);
    send('click', [evt.button, 0, pos.x, pos.y]);
}, false);

canvas.addEventListener('mouseup', function(evt) {
    evt.preventDefault();
    var button = 'right';
    var pos = getMousePos(canvas, evt);
    send('click', [evt.button, 1, pos.x, pos.y]);
}, false);

canvas.addEventListener('contextmenu', function(evt) {
    evt.preventDefault();
}, false);

canvas.addEventListener('wheel', function(evt) {
    evt.preventDefault();
    send('wheel', [evt.deltaY]);
}, false);
