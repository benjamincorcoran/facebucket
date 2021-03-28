function demo_create() {
    var ref = $('#dialogtree').jstree(true),
        sel = ref.get_selected();
    if(!sel.length) { return false; }
    sel = sel[0];
    n = ref.get_node(sel)
    if(n.type == 'user'){
        sel = ref.create_node(sel, {"type":"bucket", "text":"<BUCKET RESPONSE>"});
    } else {
        sel = ref.create_node(sel, {"type":"user", "text":"<TRIGGER PHRASE>"})
        sel = ref.create_node(sel, {"type":"bucket", "text":"<BUCKET RESPONSE>"})
    }
    
    if(sel) {
        ref.edit(sel);
    }
};
function demo_rename() {
    var ref = $('#dialogtree').jstree(true),
        sel = ref.get_selected();
    if(!sel.length) { return false; }
    sel = sel[0];
    ref.edit(sel);
};
function demo_delete() {
    var ref = $('#dialogtree').jstree(true),
        sel = ref.get_selected();
    if(!sel.length) { return false; }
    ref.delete_node(sel);
};

function eachRecursive(obj, i=0, tree={})
{

    for (i in obj['children'][0]['children']){
        console.log(obj['text'], obj['children'][0]['children'][i])
        if (obj['children'][0]['children'][i]['children'][0]['children'].length == 0){
            tree[obj['children'][0]['children'][i]['text']] = obj['children'][0]['children'][i]['children'][0]['text']
        } else {
            tree[obj['children'][0]['children'][i]['text']] = eachRecursive(obj['children'][0]['children'][i])
        }
    }
    
    trigger = obj['text'];
    response = obj['children'][0]['text'];

    return [trigger, response, tree]
}

function get_json() {
    var ref = $('#dialogtree').jstree(true);
    var tree = ref.get_json('#',{'no_state':true,'no_id':true,'no_data':true,'no_li_attr':true,'no_a_attr':true})[0];

    var json = eachRecursive(tree);
    var trig = json[0];
    var json = json.slice(1,3);
    $('#dialogJson')[0].innerHTML = 'IF '+trig+' TREE '+JSON.stringify(json)
};



$('#dialogtree')								.jstree({
    "core" : {
        "animation" : 0,
        "check_callback" : true,
        'force_text' : true,
        "themes" : { "stripes" : true },
        'data' : [
            {
              'text' : '<TRIGGER PHRASE>',
              'type':'user',
              'state' : {
                'opened' : true,
                'selected' : true
              },
              'children' : [
                {'text':'<BUCKET RESPONSE>', 'type':'bucket','children' : [
                    {'text':'<TRIGGER PHRASE>', 'type':'user','children' : [
                        {'text':'<BUCKET RESPONSE>', 'type':'bucket'}
                      ]}
                  ]}
              ]
           }
         ]
    },
    "types" : {
        "#" : { "max_children" : 1, "max_depth" : 10, "valid_children" : ["root"] },
        "root" : { "icon" : "/static/3.3.11/assets/images/tree_icon.png", "valid_children" : ["bucket"] },
        "bucket" : { "icon" : "themes/bucket.png", "valid_children" : ["user"] },
        "user" : { "max_children" : 1, "icon" : "themes/user.png", "valid_children" : ["bucket"] }
    },
    "plugins" : [ "contextmenu", "dnd", "search", "state", "types", "wholerow" ]
});



