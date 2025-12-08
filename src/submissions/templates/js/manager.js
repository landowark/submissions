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

