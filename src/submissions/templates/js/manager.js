
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
    console.log("Currently editting:", editting);
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

function moveOptions(sourceListId, destinationListId, data, form) {
    field = sourceListId.split("_")[0];
    console.log("Moving", field, "options from", sourceListId, "to", destinationListId);
    var sourceList = document.getElementById(sourceListId);
    var destinationList = document.getElementById(destinationListId);
    var manage_name = document.getElementById('ObjectName').innerText.replace('Manage ', '');
    var editting = document.getElementById('name').value;
    Array.from(sourceList.selectedOptions).forEach(option => {
        if (sourceListId.includes("available")) {
            if (form) {
                if (!form.id.includes("association_Form")) {
                    backend.add_relationship(field, option.value, data);
                } else {
                    console.warn("Not going to add relationship for association")
                }
            } else {
                backend.add_relationship(field, option.value, data);
            }
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

function get_association_form_data(association_form, field) {
    if (!association_form) return null;

    var formdata = new FormData(association_form);

    if (association_form.id.includes("association")) {
        console.log("This is an association.");
        
        // 1. Find the containers
        let containers = association_form.querySelectorAll(".dual-listbox-container");
        
        containers.forEach(container => {
            // 2. Target the specific select element with the 'selected' class
            let selectElement = container.querySelector("select.selected");
            
            if (selectElement) {
                // 3. Map the options correctly
                let optionValues = Array.from(selectElement.options).map(opt => opt.value);
                
                optionValues.forEach(val => formdata.append(container.id, val));
            }
        });
    }

    // 4. Handle multiple values correctly
    // Object.fromEntries only keeps the last value for duplicate keys.
    // Use this logic to ensure arrays stay as arrays:
    var formObject = {};
    
    // Iterate unique keys to build the final object
    for (let key of new Set(formdata.keys())) {
        let allValues = formdata.getAll(key);
        
        // Check if this key belongs to a dual-listbox container
        const isListBox = document.getElementById(key)?.classList.contains('dual-listbox-container');

        // Logic: If it's a listbox OR has multiple values, store as an array.
        // Otherwise, store as a single value (string/file).
        if (isListBox || allValues.length > 1) {
            formObject[key] = allValues;
        } else {
            formObject[key] = allValues[0];
        }
    }


    console.log("Form object: ", JSON.stringify(formObject, null, 4));
    return formObject;
}


// Replace per-button attachment with delegated handler
function setupDualListDelegation() {
    const container = document.getElementById('object_form');
    if (!container || container.dataset.dualListHandlerAttached) return;
    container.addEventListener('click', (e) => {
        const t = e.target;
        container.dataset.dualListHandlerAttached = 'true';
        
        if (t.classList && t.classList.contains('addSelectedBtn')) {
            e.preventDefault();
            console.log("Add button clicked (delegated):", t.name);
            this_form = document.getElementById(`${t.name}association_Form`);
            let data = {};
            if (this_form) {
                data = get_association_form_data(form=this_form, field=t.name);
            }
            moveOptions(`${t.name}_availableOptions`, `${t.name}_selectedOptions`, data, t.form);
        } else if (t.classList && t.classList.contains('removeSelectedBtn')) {
            e.preventDefault();
            console.log("Remove button clicked (delegated):", t.name);
            moveOptions(`${t.name}_selectedOptions`, `${t.name}_availableOptions`);
        } else {
            return;
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
        document.getElementById(field + 'association_Form').innerHTML = html;
        backend.save_html()
    });
}
