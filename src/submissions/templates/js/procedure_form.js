




var formchecks = document.getElementsByClassName('form_check');

for(let i = 0; i < formchecks.length; i++) {
  formchecks[i].addEventListener("change", function() {
    backend.check_toggle(formchecks[i].id, formchecks[i].checked);
  })
};

var formtexts = document.getElementsByClassName('form_text');

for(let i = 0; i < formtexts.length; i++) {
  formtexts[i].addEventListener("input", function() {
    backend.text_changed(formtexts[i].id, formtexts[i].value);
  })
};

var repeat_box = document.getElementById("repeat");

repeat_box.addEventListener("input", function() {
    backend.check_toggle("repeat", repeat_box.checked)
    var repeat_str = document.getElementById("repeat_of");
    if (repeat_box.checked) {
        repeat_str.classList.remove("hidden_input");
    } else {
        repeat_str.classList.add("hidden_input");
    }
})

var repeat_of = document.getElementById("repeat_of");

repeat_of.addEventListener("change", function() {
    backend.text_changed("repeat_of", repeat_of.value)
})

var changed_it = new Event('change');

const reagentRoles = document.getElementsByClassName("reagentrole_container");

for(let i = 0; i < reagentRoles.length; i++) {
  var rr = reagentRoles[i].querySelector(".reagentrole");
  rr.addEventListener("change", async function() {
    if (rr.value.includes("--New--")) {
        // alert("Create new reagent.")
        var br = document.createElement("br");
        var new_reg = document.getElementById("new_" + rr.id);
        var new_form = document.createElement("form");
        new_form.setAttribute("class", "new_reagent_form")
        new_form.setAttribute("id", rr.id + "_addition")
        var rr_name = document.createElement("select");
        rr_name.setAttribute("id", "new_" + rr.id + "_name");
        var rr_options = await backend.get_reagent_names(rr.id).then(
            function(result) {
                result.forEach( function(item) {
                    rr_name.options.add( new Option(item));
                });
            }
        );
        var rr_name_label = document.createElement("label");
        rr_name_label.setAttribute("for", "new_" + rr.id + "_name");
        rr_name_label.innerHTML = "Name:";
        var rr_lot = document.createElement("input");
        rr_lot.setAttribute("type", "text");
        rr_lot.setAttribute("id", "new_" + rr.id + "_lot");
        var rr_lot_label = document.createElement("label");
        rr_lot_label.setAttribute("for", "new_" + rr.id + "_lot");
        rr_lot_label.innerHTML = "Lot:";
        var rr_expiry = document.createElement("input");
        rr_expiry.setAttribute("type", "date");
        rr_expiry.setAttribute("id", "new_" + rr.id + "_expiry");
        var rr_expiry_label = document.createElement("label");
        rr_expiry_label.setAttribute("for", "new_" + rr.id + "_expiry");
        rr_expiry_label.innerHTML = "Expiry:";
        var submit_btn = document.createElement("input");
        submit_btn.setAttribute("type", "submit");
        submit_btn.setAttribute("value", "Submit");
        new_form.appendChild(br.cloneNode());
        new_form.appendChild(rr_name_label);
        new_form.appendChild(rr_name);
        new_form.appendChild(br.cloneNode());
        new_form.appendChild(rr_lot_label);
        new_form.appendChild(rr_lot);
        new_form.appendChild(br.cloneNode());
        new_form.appendChild(rr_expiry_label);
        new_form.appendChild(rr_expiry);
        new_form.appendChild(br.cloneNode());
        new_form.appendChild(submit_btn);
        new_form.appendChild(br.cloneNode());
        new_form.onsubmit = function(event) {
            event.preventDefault();
            name = document.getElementById("new_" + rr.id + "_name").value;
            lot = document.getElementById("new_" + rr.id + "_lot").value;
            expiry = document.getElementById("new_" + rr.id + "_expiry").value;
            backend.add_new_reagent(rr.id, name, lot, expiry);
            new_form.remove();
//            reagentRoles[i].dispatchEvent(changed_it);
        }
        new_reg.appendChild(new_form);
    } else {
        var checkbox = reagentRoles[i].querySelector(".procedure_checkbox"); 
        console.log("Checkbox for reagent role:", rr.id, checkbox);  
        backend.update_reagent(rr.id, rr.value, checkbox.checked);
        newregform = document.getElementById(rr.id + "_addition");
        try {
            newregform.remove();
        }
        catch(err) {
            console.log("Missed it.");
        }
    }
  });
};

var checkboxes = document.getElementsByClassName("procedure_checkbox");

for(let i = 0; i < checkboxes.length; i++) {

    checkboxes[i].addEventListener("input", function() {
        neighbour = document.getElementById(checkboxes[i].name);
        neighbour.disabled = !checkboxes[i].checked;
        if (neighbour.classList.contains("equipmentrole")) {
            process = document.getElementById(checkboxes[i].name + "_process");
            process.disabled = !checkboxes[i].checked;
            tips = document.getElementById(checkboxes[i].name + "_tips");
            tips.disabled = !checkboxes[i].checked;
            backend.update_equipment(neighbour.name, neighbour.value, process.value, tips.value, checkboxes[i].checked);
        } else if (neighbour.classList.contains("reagentrole")) {
            backend.update_reagent(neighbour.name, neighbour.value, checkboxes[i].checked);
        };
    });
}

var equipmentroles = document.getElementsByClassName("equipmentrole");



window.addEventListener('load', function () {
    if (typeof QWebChannel !== 'undefined') {
        new QWebChannel(qt.webChannelTransport, function (channel) {
            // This callback runs *after* the connection is established
            backend = channel.objects.backend;

            if (backend) {
                console.log("Backend channel established successfully.");
                // NOW it is safe to run your startup logic
                equipment_json.forEach(equipment_startup);
                Array.prototype.forEach.call(reagentRoles, reagentrole_startup)
                // reagentRoles.forEach(reagentrole_startup);
            } else {
                console.error("Backend object not found in channel objects.");
            }
        });
    } else {
        console.error("qwebchannel.js is not loaded.");
    }
});

function reagentrole_startup(reagentrole) {
    selector = reagentrole.querySelector(".reagentrole");
    checkbox = reagentrole.querySelector(".procedure_checkbox");
    // selector.disabled = !checkbox.checked;
    backend.update_reagent(reagentrole.id, reagentrole.value, checkbox.checked);
}

function equipment_startup(equipmentrole) {
    console.log(equipmentrole);
    updateEquipmentChoices(equipmentrole);
    var eq_dropdown = document.getElementById(equipmentrole.name);
    eq_dropdown.addEventListener("change", function(event){
        updateProcessChoices(equipmentrole);
        updateBackend(equipmentrole);
    });
    var process_dropdown = document.getElementById(equipmentrole.name + "_process");
    process_dropdown.addEventListener("change", function(event){
        updateTipChoices(equipmentrole);
        updateBackend(equipmentrole);
    });
    var tips_dropdown = document.getElementById(equipmentrole.name + "_tips");
    tips_dropdown.addEventListener("change", function(event){
        updateBackend(equipmentrole);
    });
    updateBackend(equipmentrole);
}

function updateEquipmentChoices(equipmentrole) {
    console.log("Updating equipment choices.");
    var dropdown_oi = document.getElementById(equipmentrole.name);
    while (dropdown_oi.options.length > 0) {
        dropdown_oi.remove(0);
    }
    dropdown_oi.json = equipmentrole;
    for (let iii = 0; iii < equipmentrole.equipment.length; iii++) {
        var opt = document.createElement('option');
        opt.value = equipmentrole.equipment[iii];
        opt.innerHTML = equipmentrole.equipment[iii];
        dropdown_oi.appendChild(opt);
    }
    updateProcessChoices(equipmentrole);
}

function updateProcessChoices(equipmentrole) {
    console.log("Updating process choices.");
    var dropdown_oi = document.getElementById(equipmentrole.name + "_process");
    while (dropdown_oi.options.length > 0) {
        dropdown_oi.remove(0);
    }
    dropdown_oi.json = equipmentrole;
    var equipment_name = document.getElementById(equipmentrole.name).value;
    var assoc_name = equipmentrole.name + "->" + equipment_name;
    // var assoc = equipmentrole.equipmentroleequipmentassociation.filter(function(x){return x.name==assoc_name})[0];
    // var processes = assoc.process.filter(function(x){ return x.equipmentroleequipmentassociation.includes(assoc_name) });
    var assoc = equipmentrole.equipmentroleequipmentassociation.find(function(x){return x.name==assoc_name});
    if (!assoc) { return }
    var processes = assoc.process;
    for (let iii = 0; iii < processes.length; iii++) {
        for (let jjj = 0; jjj < processes[iii].processversion.length; jjj++) {
            var output = processes[iii].processversion[jjj];
            if (Boolean(output.active)) {
                var opt = document.createElement('option');
                opt.value = output.name;
                opt.innerHTML = output.name;
                dropdown_oi.appendChild(opt);
            }
        }
    }
    updateTipChoices(equipmentrole);
}

function updateTipChoices(equipmentrole) {
    console.log("Updating tip choices.");
    var dropdown_oi = document.getElementById(equipmentrole.name + "_tips");
    while (dropdown_oi.options.length > 0) {
        dropdown_oi.remove(0);
    }
    dropdown_oi.json = equipmentrole;
    var equipment_name = document.getElementById(equipmentrole.name).value;
    var assoc_name = equipmentrole.name + "->" + equipment_name;
    // var assoc = equipmentrole.equipmentroleequipmentassociation.filter(function(x){return x.name==assoc_name})[0];
    // var processes = assoc.process.filter(function(x){ return x.equipmentroleequipmentassociation.includes(assoc_name) });
    var assoc = equipmentrole.equipmentroleequipmentassociation.find(function(x){return x.name==assoc_name});
    if (!assoc) { return }
    var processes = assoc.process;
    for (let iii = 0; iii < processes.length; iii++) {
        for (let jjj = 0; jjj < processes[iii].tips.length; jjj++) {
            var output = processes[iii].tips[jjj];
            if (Boolean(output.active)) {
                var opt = document.createElement('option');
                opt.value = output.name;
                opt.innerHTML = output.name;
                dropdown_oi.appendChild(opt);
            }
        }
    }
}

function getSelectValues(select) {
    var result = [];
    var options = select && select.options;
    var opt;

    for (var i=0, iLen=options.length; i<iLen; i++) {
        opt = options[i];

        if (opt.selected) {
        result.push(opt.value || opt.text);
        }
    }
    return result;
}

function updateBackend(equipmentrole) {
    var equipmentrole_name = equipmentrole.name
    var dropdown_oi = document.getElementById(equipmentrole.name);
    var equipment_name = dropdown_oi.value;
    dropdown_oi = document.getElementById(equipmentrole.name + "_process");
    var process_name = dropdown_oi.value;
    dropdown_oi = document.getElementById(equipmentrole.name + "_tips");
    var tips_names = getSelectValues(dropdown_oi);;

    console.log("Updating backend with:", equipmentrole_name, equipment_name, process_name, tips_names);
    backend.update_equipment(equipmentrole_name, equipment_name, process_name, tips_names)
}

function runPreprocessFunction(element) {
    backend.run_preprocess_function(element.innerText);
}

var dateInputs = document.querySelectorAll('input.date_change');
    dateInputs.forEach(function(input) {
        input.addEventListener('change', function() {
            var id = this.id.replace('_dc', '');
            var newValue = this.value;
            console.log('Date changed for:', id, 'New value:', newValue);
            backend.update_date(id, newValue);
        });
    });

// window.onload = function() {
//     for(let i = 0; i < reagentRoles.length; i++) {
//         console.log("Updating reagent:", reagentRoles[i].id, reagentRoles[i].value)
//         backend.update_reagent(reagentRoles[i].id, reagentRoles[i].value);
//     }

// }

