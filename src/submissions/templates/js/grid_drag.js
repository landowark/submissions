

const gridContainer = document.getElementById("plate-container");
let draggedItem = null;

//Handle Drag start
gridContainer.addEventListener("dragstart", (e) => {

  draggedItem = e.target;
  draggedItem.style.opacity = "0.5";
});

//Handle Drag End
gridContainer.addEventListener("dragend", (e) => {
  e.target.style.opacity = "1";
  draggedItem = null;
});

//handle dragging ove grid items
gridContainer.addEventListener("dragover", (e) => {
  e.preventDefault();
});

//Handle Drop
gridContainer.addEventListener("drop", (e) => {
  e.preventDefault();

  const targetItem = e.target;

  if (
    targetItem &&
    targetItem !== draggedItem //&&
    //targetItem.classList.contains("well")
  ) {
    backend.log(targetItem.id);
    const draggedIndex = [...gridContainer.children].indexOf(draggedItem);
    const targetIndex = [...gridContainer.children].indexOf(targetItem);
    if (draggedIndex < targetIndex) {
      backend.log(draggedIndex.toString() + " " + targetIndex.toString() + " Lesser");
      gridContainer.insertBefore(draggedItem, targetItem.nextSibling);

    } else {
      backend.log(draggedIndex.toString() + " " + targetIndex.toString() + " Greater");
      gridContainer.insertBefore(draggedItem, targetItem);

    }
//    output = [];
//    fullGrid = [...gridContainer.children];
//    fullGrid.forEach(function(item, index) {
//        output.push({sample_id: item.id, index: index + 1})
//    });
//    backend.rearrange_plate(output);
    rearrange_plate();
  }
});