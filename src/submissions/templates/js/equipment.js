const equipment_json = {{ proceduretype['equipment_json'] }};

window.addEventListener('load', function () {
    equipment_json.forEach(startup);
})

function startup(equipmentrole) {
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
}

function updateEquipmentChoices(equipmentrole) {
    console.log("Updating equipment choices.");
    var dropdown_oi = document.getElementById(equipmentrole.name);
    // remove old options
    while (dropdown_oi.options.length > 0) {
        dropdown_oi.remove(0);
    }
    dropdown_oi.json = equipmentrole;
    for (let iii = 0; iii < equipmentrole.equipmentroleequipmentassociation.equipment.length; iii++) {
        var opt = document.createElement('option');
        opt.value = equipmentrole.equipmentroleequipmentassociation.equipment[iii].name;
        opt.innerHTML = equipmentrole.equipmentroleequipmentassociation.equipment[iii].name;
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
    var assoc_name = equipmentrole.name + "->" + equipment_name
    console.log("Equipment for process: " + assoc_name)
    var processes = equipmentrole.equipmentroleequipmentassociation.process.filter(function(x){ return assoc_name in x.equipmentroleequipmentassociation })[0];
    for (let iii = 0; iii < processes.length; iii++) {
        for (let jjj = 0; jjj < processes[iii].processversion.length; jjj++) {
            var output = processes[iii].processversion[jjj]
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
    dropdown_oi.innerHTML = "";
    dropdown_oi.json = equipmentrole;
    var equipment_name = document.getElementById(equipmentrole.name).value;
    var process_name = document.getElementById(equipmentrole.name + "_process").value;
    console.log(process_name);
    var equipment = equipmentrole.equipment.filter(function(x){ return x.name == equipment_name })[0];
    console.log(equipment);
    var process = equipment.processes.filter(function(x){ return x.name == process_name })[0];
    console.log(process);
    for (let iii = 0; iii < process.tips.length; iii++) {
        var opt = document.createElement('option');
        opt.value = process.tips[iii];
        opt.innerHTML = process.tips[iii];
        dropdown_oi.appendChild(opt);
    }
}

function updateBackend(equipmentrole) {
    alert("Updating Backend");
    var equipmentrole_name = equipmentrole.name
    var dropdown_oi = document.getElementById(equipmentrole.name);
    var equipment_name = dropdown_oi.value;
    dropdown_oi = document.getElementById(equipmentrole.name + "_process");
    var process_name = dropdown_oi.value;
    dropdown_oi = document.getElementById(equipmentrole.name + "_tips");
    var tips_name = dropdown_oi.value;
    backend.update_equipment(equipmentrole_name, equipment_name, process_name, tips_name)
}
