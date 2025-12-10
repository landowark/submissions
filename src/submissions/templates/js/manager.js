// function update_selection(value) {
//     // Handle the selection change
//     console.log("Selected value:", value);
//     backend.update_selection(value);
//     // You can add more logic here to update the UI based on the selected value
// }

// const initSelectionDropdown = document.getElementById('inital_object');

// initSelectionDropdown.addEventListener('change', (event) => {
//     var selectedValue = event.target.value;
//     console.log("Dropdown changed, selected value:", selectedValue);
//     if (backend) {
//         backend.update_selection(selectedValue);
//     } else {
//         console.warn('Backend is not available yet.');
//     }
// });

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
    backend.update_instrumentedattribute(field, value);
}

function moveOptions(sourceListId, destinationListId) {
    field = sourceListId.split("_")[0];
    console.log("Moving", field, "options from", sourceListId, "to", destinationListId);
    var sourceList = document.getElementById(sourceListId);
    var destinationList = document.getElementById(destinationListId);
    Array.from(sourceList.selectedOptions).forEach(option => {
        destinationList.appendChild(option);
        if (sourceListId.includes("available")) {
            backend.add_relationship(field, option.value);
        } else if (sourceListId.includes("selected")) {
            backend.remove_relationship(field, option.value);
        }
    });
}

// Replace per-button attachment with delegated handler
function setupDualListDelegation() {
    const container = document.getElementById('object_form');
    if (!container || container.dataset.dualListHandlerAttached) return;
    container.addEventListener('click', (e) => {
        const t = e.target;
        if (t.classList && t.classList.contains('addSelectedBtn')) {
            e.preventDefault();
            console.log("Add button clicked (delegated):", t.name);
            moveOptions(`${t.name}_availableOptions`, `${t.name}_selectedOptions`);
        } else if (t.classList && t.classList.contains('removeSelectedBtn')) {
            e.preventDefault();
            console.log("Remove button clicked (delegated):", t.name);
            moveOptions(`${t.name}_selectedOptions`, `${t.name}_availableOptions`);
        }
    });

    container.dataset.dualListHandlerAttached = 'true';
}

// initialize for any static content on load
document.addEventListener('DOMContentLoaded', () => {
    setupDualListDelegation();
});

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


