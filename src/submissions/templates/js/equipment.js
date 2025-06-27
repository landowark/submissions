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
    while (dropdown_oi.options.length > 0) {
        dropdown_oi.remove(0);
    }
    dropdown_oi.json = equipmentrole;
    for (let iii = 0; iii < equipmentrole.equipment.length; iii++) {
        var opt = document.createElement('option');
        opt.value = equipmentrole.equipment[iii].name;
        opt.innerHTML = equipmentrole.equipment[iii].name;
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
    var equipment = equipmentrole.equipment.filter(function(x){ return x.name == equipment_name })[0];
    for (let iii = 0; iii < equipment.processes.length; iii++) {
        var opt = document.createElement('option');
        opt.value = equipment.processes[iii].name;
        opt.innerHTML = equipment.processes[iii].name;
        dropdown_oi.appendChild(opt);
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
