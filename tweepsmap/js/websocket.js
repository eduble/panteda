
// websocket management
var callbacks = {};
var next_cb_idx = 0;
var free_ws = [];
var window_loaded = false;

function get_ws_url() {
    var loc = window.location, proto;
    if (loc.protocol === "https:") {
        proto = "wss:";
    } else {
        proto = "ws:";
    }
    return proto + "//" + loc.host + "/websockets/rpc";
}

function ws_onmessage(evt) {
    // parse the message
    var json = JSON.parse(evt.data);
    var cb_idx = json[0];
    var result = json[1];
    var callback = callbacks[cb_idx];
    // callbacks[cb_idx] will no longer be needed
    delete callbacks[cb_idx];
    // we have the result, thus this websocket is free again
    free_ws.push(callback.ws);
    // call the callback that was given with the request
    callback(result);
}

function ws_request(func_name, args, kwargs, callback)
{
    var ws;
    // firefox fails if we call ws API too early
    if (window_loaded == false)
    {
        // restart the call when window is loaded
        add_window_onload(function() {
            ws_request(func_name, args, kwargs, callback)
        });
        return;
    }

    // check if we have at least one websocket free
    if (free_ws.length == 0)
    {   // existing websockets are busy, create new one
        ws = new WebSocket(get_ws_url());
        ws.onmessage = ws_onmessage;
        ws.onopen = function() {
            free_ws.push(ws);
            // restart the call
            ws_request(func_name, args, kwargs, callback)
        }
        ws.onerror = function() {
            console.log("ws error!");
        }
        return;
    }
    // everything is fine, continue
    // get a callback id
    var cb_idx = next_cb_idx;
    next_cb_idx += 1;
    // pop one of the free websockets
    ws = free_ws.pop();
    // attach the websocket we will use to the callback, for later reference
    callback.ws = ws;
    // record the callback using its id
    callbacks[cb_idx] = callback;
    // prepare the message and send it
    var msg = JSON.stringify([ cb_idx, [func_name], args, kwargs ]);
    ws.send(msg);
}

function add_window_onload(cb)
{
    var prev_onload = window.onload;
    window.onload = function () {
        if (prev_onload) {
            prev_onload();
        }
        cb();
    };
}

add_window_onload(function() {
    window_loaded = true;
});

