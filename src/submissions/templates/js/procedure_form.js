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