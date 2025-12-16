
async function update_selection(value) {
    console.log("Selected value:", value);  
    if (backend) {
        await backend.update_selection(value).then((html) => {
            document.getElementById('object_form').innerHTML = html;
        })
    } else {
        console.warn('Backend is not available yet.');
    }      
    backend.save_html(); 
}

function instumentedattribute_change(field, value) {
    console.log("Field changed:", field, "New value:", value);
    var editting = document.getElementById('name');
    try {
        if (editting.value === "Default SubmissionType") {
            alert("Cannot modify Default SubmissionType.");
            return; // Prevent changes to Default SubmissionType
        }
    } catch (error) {
        console.error("Error occurred:", error.message);
    }
    backend.update_instrumentedattribute(field, value);
}

function moveOptions(sourceListId, destinationListId, data) {
    field = sourceListId.split("_")[0];
    console.log("Moving", field, "options from", sourceListId, "to", destinationListId);
    var sourceList = document.getElementById(sourceListId);
    var destinationList = document.getElementById(destinationListId);
    var manage_name = document.getElementById('ObjectName').innerText.replace('Manage ', '');
    var editting = document.getElementById('name').value;
    Array.from(sourceList.selectedOptions).forEach(option => {
        if (sourceListId.includes("available")) {
            backend.add_relationship(field, option.value, data);
        } else if (sourceListId.includes("selected")) {
            if (option.value === "Default SubmissionType" && ["ProcedureType"].includes(manage_name)) {
                alert("Cannot remove default submission type.");
                return; // Skip moving the default option
            } else if (editting === "Default SubmissionType" && field === "proceduretype" && destinationListId.includes("available")) {
                alert("Can't remove procedure types from Default SubmissionType.");
                return; // Skip moving the default option
            } else {
                backend.remove_relationship(field, option.value);
            }
        }
        destinationList.appendChild(option);
    });
}

// Replace per-button attachment with delegated handler
function setupDualListDelegation() {
    const container = document.getElementById('object_form');
    if (!container || container.dataset.dualListHandlerAttached) return;
    container.addEventListener('click', (e) => {
        const t = e.target;
        var association_form = document.getElementById(t.name + '_associationForm');
        if (association_form) {
            var formdata = new FormData(association_form);
        } else {
            var formdata = null;
        }
        if (formdata) {
            // var eds = document.getElementById(t.name + '_availableOptions');
            // if (eds) {
            //     formdata.append(t.name, eds.selectedOptions[0].text);
            // }
            // var manage_name = document.getElementById('ObjectName').innerText.replace('Manage ', '').toLowerCase();
            // var editting = document.getElementById('initial_object').value;
            // formdata.append(manage_name, editting);
            formdata.forEach((value, key) => {
                console.log('Form data:', key, value);
            });
            var formObject = Object.fromEntries(formdata.entries());
        } else {
            var formObject = null;
        }
        if (t.classList && t.classList.contains('addSelectedBtn')) {
            e.preventDefault();
            console.log("Add button clicked (delegated):", t.name);
            moveOptions(`${t.name}_availableOptions`, `${t.name}_selectedOptions`, formObject);
        } else if (t.classList && t.classList.contains('removeSelectedBtn')) {
            e.preventDefault();
            console.log("Remove button clicked (delegated):", t.name);
            moveOptions(`${t.name}_selectedOptions`, `${t.name}_availableOptions`, formObject);
        }
    });
    container.dataset.dualListHandlerAttached = 'true';
}

// initialize for any static content on load
document.addEventListener('DOMContentLoaded', () => {
    setupDualListDelegation();
});

async function createAssociationForm(field, selectedValue) {
    console.log("Creating association form for field:", field, "and selected value:", selectedValue);
    await backend.get_association_form(field, selectedValue).then((html) => {
        document.getElementById(field + '_associationForm').innerHTML = html;
    });
}

// Example usage for a button click
// var addButtons = document.getElementsByClassName('addSelectedBtn');
// var removeButtons = document.getElementsByClassName('removeSelectedBtn');

// for (let i = 0; i < addButtons.length; i++) {
//     addButtons[i].addEventListener('click', (e) => {
//         e.preventDefault();
//         console.log("Add button clicked:", addButtons[i].name);
//         moveOptions(addButtons[i].name + '_availableOptions', addButtons[i].name + '_selectedOptions');
//     });
// };

// for (let i = 0; i < removeButtons.length; i++) {
//     removeButtons[i].addEventListener('click', (e) => {
//         e.preventDefault();
//         console.log("Remove button clicked:", removeButtons[i].name);
//         moveOptions(removeButtons[i].name + '_selectedOptions', removeButtons[i].name + '_availableOptions');
//     });
// }

// document.getElementById('addButton').addEventListener('click', () => {
//   moveOptions('availableOptions', 'selectedOptions');
// });

// document.getElementById('removeButton').addEventListener('click', () => {
//   moveOptions('selectedOptions', 'availableOptions');
// });


