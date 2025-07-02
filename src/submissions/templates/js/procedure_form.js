


document.getElementById("kittype").addEventListener("change", function() {
    backend.update_kit(this.value);
})

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

var changed_it = new Event('change');

var reagentRoles = document.getElementsByClassName("reagentrole");

for(let i = 0; i < reagentRoles.length; i++) {
  reagentRoles[i].addEventListener("change", function() {
    if (reagentRoles[i].value.includes("--New--")) {
        alert("Create new reagent.")
        var br = document.createElement("br");
        var new_reg = document.getElementById("new_" + reagentRoles[i].id);
        var new_form = document.createElement("form");
        new_form.setAttribute("class", "new_reagent_form")
        new_form.setAttribute("id", reagentRoles[i].id + "_addition")
        var rr_name = document.createElement("input");
        rr_name.setAttribute("type", "text");
        rr_name.setAttribute("id", "new_" + reagentRoles[i].id + "_name");
        var rr_name_label = document.createElement("label");
        rr_name_label.setAttribute("for", "new_" + reagentRoles[i].id + "_name");
        rr_name_label.innerHTML = "Name:";
        var rr_lot = document.createElement("input");
        rr_lot.setAttribute("type", "text");
        rr_lot.setAttribute("id", "new_" + reagentRoles[i].id + "_lot");
        var rr_lot_label = document.createElement("label");
        rr_lot_label.setAttribute("for", "new_" + reagentRoles[i].id + "_lot");
        rr_lot_label.innerHTML = "Lot:";
        var rr_expiry = document.createElement("input");
        rr_expiry.setAttribute("type", "date");
        rr_expiry.setAttribute("id", "new_" + reagentRoles[i].id + "_expiry");
        var rr_expiry_label = document.createElement("label");
        rr_expiry_label.setAttribute("for", "new_" + reagentRoles[i].id + "_expiry");
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
            name = document.getElementById("new_" + reagentRoles[i].id + "_name").value;
            lot = document.getElementById("new_" + reagentRoles[i].id + "_lot").value;
            expiry = document.getElementById("new_" + reagentRoles[i].id + "_expiry").value;
            backend.add_new_reagent(reagentRoles[i].id, name, lot, expiry);
            new_form.remove();
//            reagentRoles[i].dispatchEvent(changed_it);
        }
        new_reg.appendChild(new_form);
    } else {
        newregform = document.getElementById(reagentRoles[i].id + "_addition");
        try {
            newregform.remove();
        }
        catch(err) {
            console.log("Missed it.");
        }
        alert(reagentRoles[i].value);
        backend.update_reagent(reagentRoles[i].id, reagentRoles[i].value);


    }
  });
};

window.onload = function() {
    for(let i = 0; i < reagentRoles.length; i++) {
        backend.update_reagent(reagentRoles[i].id, reagentRoles[i].value);
    }
}

