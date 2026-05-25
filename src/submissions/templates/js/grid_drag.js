

const gridContainer = document.getElementById("plate-container");
let draggedItem = null;

//Handle Drag start
gridContainer.addEventListener("dragstart", (e) => {

  draggedItem = e.target.closest('.well');
  draggedItem.style.opacity = "0.5";
});

//Handle Drag End
gridContainer.addEventListener("dragend", (e) => {
  draggedItem.style.opacity = "1";
  draggedItem = null;
});

//handle dragging ove grid items
gridContainer.addEventListener("dragover", (e) => {
  e.preventDefault();
});

//Handle Drop
gridContainer.addEventListener("drop", (e) => {
  e.preventDefault();
  console.log("Drag and drop")
  const targetItem = e.target.closest('.well');

  if (
    targetItem &&
    targetItem !== draggedItem //&&
    //targetItem.classList.contains("well")
  ) {
//    backend.log(targetItem.id);
    const draggedIndex = [...gridContainer.children].indexOf(draggedItem);
    const targetIndex = [...gridContainer.children].indexOf(targetItem);
    if (draggedIndex < targetIndex) {
//      backend.log(draggedIndex.toString() + " " + targetIndex.toString() + " Lesser");
      gridContainer.insertBefore(draggedItem, targetItem.nextSibling);

    } else {
//      backend.log(draggedIndex.toString() + " " + targetIndex.toString() + " Greater");
      gridContainer.insertBefore(draggedItem, targetItem);

    }
    output = [];
    fullGrid = [...gridContainer.children];
    fullGrid.forEach(function(item, index) {
        output.push({sample_id: item.id, index: index + 1, class: item.className});
    });
    // backend.rearrange_plate(output);
    rearrange_plate();
  }
});