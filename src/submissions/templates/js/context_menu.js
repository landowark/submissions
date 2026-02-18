
///////////////////////////////////////
///////////////////////////////////////
//
// H E L P E R F U N C T I O N S
//
///////////////////////////////////////
///////////////////////////////////////

function clickInsideElement( e, className ) {
    var el = e.srcElement || e.target;
    if ( el.classList.contains(className) ) {
        return el;
    } else {
        while ( el = el.parentNode ) {
            if ( el.classList && el.classList.contains(className) ) {
                return el;
            }
        }
    }
    return false;
}

function getPosition(e) {
    var posx = 0;
    var posy = 0;
    if (!e) var e = window.event;
    if (e.pageX || e.pageY) {
        posx = e.pageX;
        posy = e.pageY;
    } else if (e.clientX || e.clientY) {
        posx = e.clientX + document.body.scrollLeft + document.documentElement.scrollLeft;
        posy = e.clientY + document.body.scrollTop + document.documentElement.scrollTop;
    }
    return {
        x: posx,
        y: posy
    }
}

// updated positionMenu function
function positionMenu(e) {
    clickCoords = getPosition(e);
    clickCoordsX = clickCoords.x;
    clickCoordsY = clickCoords.y;
    menuWidth = menu.offsetWidth + 4;
    menuHeight = menu.offsetHeight + 4;
    windowWidth = window.innerWidth;
    windowHeight = window.innerHeight;
    if ( (windowWidth - clickCoordsX) < menuWidth ) {
        menu.style.left = windowWidth - menuWidth + "px";
    } else {
        menu.style.left = clickCoordsX + "px";
    }
    if ( (windowHeight - clickCoordsY) < menuHeight ) {
        menu.style.top = windowHeight - menuHeight + "px";
    } else {
        menu.style.top = clickCoordsY + "px";
    }
}

function menuItemListener( link ) {
    const contextIndex = [...gridContainer.children].indexOf(taskItemInContext);
    const task_id = taskItemInContext.getAttribute("id");
    switch (link.getAttribute("data-action")) {
        case "InsertSample":
            insertSample(contextIndex, task_id);
        break;
        case "InsertEN":
            insertEN(taskItemInContext);
        break;
        case "InsertPositive":
            insertPositive(taskItemInContext);
        break;
        case "InsertNegative":
            insertNegative(taskItemInContext);
        break;
        case "RemoveSample":
            removeSample(taskItemInContext);
        break;
        default:
            backend.log("default");
        break;
    }

    rearrange_plate();

    toggleMenuOff();

}


function gatherWellsText() {
    var container = document.getElementById('plate-container');
    if (!container) return '';
    var wells = container.querySelectorAll('div.well');
    var parts = [];
    wells.forEach(function(well, idx){
        var ps = well.querySelectorAll('p');
        var texts = [];
        ps.forEach(function(p){
            var t = p.innerText || p.textContent || '';
            t = t.trim();
            if (t) texts.push(t);
        });
        if (texts.length) {
        parts.push('<div class="well-block"><h4>Well ' + (idx+1) + '</h4><p>' + texts.join('</p><p>') + '</p></div>');
        }
    });
    openPrintWindow(parts.join(''));
    

    function openPrintWindow(html) {
        var printWindow = window.open('', '_blank', 'width=800,height=600');
        if (!printWindow) { console.error('Popup blocked'); return; }
        printWindow.document.open();
        printWindow.document.write('<!doctype html><html><head><title>Print wells</title><style>body{font-family: Arial, sans-serif;padding:20px} .well-block{border-bottom:1px solid #ccc;margin-bottom:12px;padding-bottom:8px} .well-block h4{margin:0 0 6px 0;font-size:14px} .well-block p{margin:0 0 4px 0}</style></head><body>' + html + '</body></html>');
        printWindow.document.close();
        printWindow.focus();
        setTimeout(function(){ printWindow.print(); }, 250);
    }

    // document.addEventListener('DOMContentLoaded', function(){
    // var btn = document.getElementById('print-wells-btn');
    // if (!btn) return;
    //     btn.addEventListener('click', function(){
    //         var html = gatherWellsText();
    //         if (!html) {
    //         alert('No <p> content found in wells.');
    //         return;
    //         }
    //         openPrintWindow(html);
    //     });
    };

///////////////////////////////////////
///////////////////////////////////////
//
// C O R E F U N C T I O N S
//
///////////////////////////////////////
///////////////////////////////////////
/**
* Variables.
*/
var contextMenuClassName = "context-menu";
var contextMenuItemClassName = "context-menu__item";
var contextMenuLinkClassName = "context-menu__link";
var contextMenuActive = "context-menu--active";
var taskItemClassName = "well";
var taskItemInContext;
var clickCoords;
var clickCoordsX;
var clickCoordsY;
var menu = document.getElementById(contextMenuClassName);
var menuItems = menu.getElementsByClassName(contextMenuItemClassName);
const menuHeader = document.getElementById("menu-header");
var menuState = 0;
var menuWidth;
var menuHeight;
var menuPosition;
var menuPositionX;
var menuPositionY;
var windowWidth;
var windowHeight;

/**
* Initialise our application's code.
*/
function init() {
    contextListener();
    clickListener();
    keyupListener();
    resizeListener();
}
/**
* Listens for contextmenu events.
*/
function contextListener() {
    document.addEventListener( "contextmenu", function(e) {
        taskItemInContext = clickInsideElement( e, taskItemClassName );
        if ( taskItemInContext ) {
            e.preventDefault();
            menuHeader.innerText = taskItemInContext.id;
            toggleMenuOn();
            positionMenu(e);
        } else {
            taskItemInContext = null;
            menuHeader.text = "";
            toggleMenuOff();
        }
    });
}

/**
* Listens for click events.
*/
function clickListener() {
    document.addEventListener( "click", function(e) {
        var clickeElIsLink = clickInsideElement( e, contextMenuLinkClassName );

        if ( clickeElIsLink ) {
            e.preventDefault();
            menuItemListener( clickeElIsLink );
        } else {
            var button = e.which || e.button;
            if ( button === 1 ) {
                toggleMenuOff();
            }
        }
    });
}
/**
* Listens for keyup events.
*/
function keyupListener() {
    window.onkeyup = function(e) {
    if ( e.keyCode === 27 ) {
        toggleMenuOff();
        }
    }
}
/**
* Turns the custom context menu on.
*/
function toggleMenuOn() {
    if ( menuState !== 1 ) {
        menuState = 1;
        menu.classList.add(contextMenuActive);
    }
}
function toggleMenuOff() {
    if ( menuState !== 0 ) {
        menuState = 0;
        menu.classList.remove(contextMenuActive);
    }
}

///////////////////////////////////////
///////////////////////////////////////
//
// B A C K E N D  F U N C T I O N S
//
///////////////////////////////////////
///////////////////////////////////////

function insertSample( index ) {
    backend.log( "Index - " + index + ", InsertSample");
}

function insertEN( targetItem ) {

    const gridC = document.getElementById("plate-container");
    var existing_ens = document.getElementsByClassName("EN");
    var en_num = existing_ens.length + 1;
    const en_name = "EN" + en_num + "-" + rsl_plate_num;
    var elem = document.createElement("div");
    elem.setAttribute("id", en_name);
    elem.setAttribute("class", "well negativecontrol EN");
    elem.setAttribute("draggable", "true");
    elem.innerHTML = '<p style="font-size: 0.7em; text-align: center; word-wrap: break-word;">' + en_name + '</p>'
    // gridC.insertBefore(elem, targetItem.nextSibling);
    gridC.insertBefore(elem, targetItem);
    // remove the target item (previous behavior: replace target with new element)
    // targetItem.remove();

    // additionally: find and remove the next element (after the original target)
    // that contains an empty <p> in its innerHTML
    try {
        const children = Array.from(gridC.children);
        // find the index where the new element currently sits
        const startIndex = children.indexOf(elem);
        if (startIndex !== -1) {
            for (let i = startIndex + 1; i < children.length; i++) {
                const child = children[i];
                const p = child.querySelector && child.querySelector('p');
                if (p) {
                    // consider <p> empty if its innerHTML is empty or only whitespace, or contains &nbsp;
                    if (p.innerHTML.trim() === '' || p.innerHTML === '&nbsp;') {
                        gridC.removeChild(child);
                        break;
                    }
                } else {
                    console.log("P element not found.");
                    gridC.removeChild(child);
                    break;
                }
            }
        }
    } catch (e) {
        // defensive: if anything goes wrong, don't block the rest of the UI
        console.error('insertPositive: error while removing next empty <p> element', e);
    }
}

function insertPositive( targetItem ) {

    const gridC = document.getElementById("plate-container");
    var existing_pos = document.getElementsByClassName("positivecontrol");
    var pos_num = existing_pos.length + 1;
    const pos_name = "PC" + pos_num + "-" + rsl_plate_num;
    var elem = document.createElement("div");
    elem.setAttribute("id", pos_name);
    elem.setAttribute("class", "well positivecontrol");
    elem.setAttribute("draggable", "true");
    elem.innerHTML = '<p style="font-size: 0.7em; text-align: center; word-wrap: break-word;">' + pos_name + '</p>'
    // insert the new positive control after the target item (keeps previous behavior)
    gridC.insertBefore(elem, targetItem);
    // remove the target item (previous behavior: replace target with new element)
    // targetItem.remove();

    // additionally: find and remove the next element (after the original target)
    // that contains an empty <p> in its innerHTML
    try {
        const children = Array.from(gridC.children);
        // find the index where the new element currently sits
        const startIndex = children.indexOf(elem);
        if (startIndex !== -1) {
            for (let i = startIndex + 1; i < children.length; i++) {
                const child = children[i];
                const p = child.querySelector && child.querySelector('p');
                if (p) {
                    // consider <p> empty if its innerHTML is empty or only whitespace, or contains &nbsp;
                    if (p.innerHTML.trim() === '' || p.innerHTML === '&nbsp;') {
                        gridC.removeChild(child);
                        break;
                    }
                } else {
                    console.log("P element not found.");
                    gridC.removeChild(child);
                    break;
                }
            }
        }
    } catch (e) {
        // defensive: if anything goes wrong, don't block the rest of the UI
        console.error('insertPositive: error while removing next empty <p> element', e);
    }
}

function insertNegative( targetItem ) {
    console.log("Insert at: " + targetItem)
    const gridC = document.getElementById("plate-container");
    var existing_neg = document.getElementsByClassName("negativecontrol");
    var neg_num = existing_neg.length + 1;
    const neg_name = "NC" + neg_num + "-" + rsl_plate_num;
    var elem = document.createElement("div");
    elem.setAttribute("id", neg_name);
    elem.setAttribute("class", "well negativecontrol");
    elem.setAttribute("draggable", "true");
    elem.innerHTML = '<p style="font-size: 0.7em; text-align: center; word-wrap: break-word;">' + neg_name + '</p>'
    // gridC.insertBefore(elem, targetItem.nextSibling);
    gridC.insertBefore(elem, targetItem);
    // remove the target item (previous behavior: replace target with new element)
    // targetItem.remove();

    // additionally: find and remove the next element (after the original target)
    // that contains an empty <p> in its innerHTML
    try {
        const children = Array.from(gridC.children);
        // find the index where the new element currently sits
        const startIndex = children.indexOf(elem);
        if (startIndex !== -1) {
            for (let i = startIndex + 1; i < children.length; i++) {
                const child = children[i];
                const p = child.querySelector && child.querySelector('p');
                if (p) {
                    // consider <p> empty if its innerHTML is empty or only whitespace, or contains &nbsp;
                    if (p.innerHTML.trim() === '' || p.innerHTML.trim() === '&nbsp;') {
                        gridC.removeChild(child);
                        break;
                    } else {
                        console.log("The p element has:", p.innerHTML)
                    }

                } else {
                    console.log("P element not found.");
                    gridC.removeChild(child);
                    break;
                }
            }
        } else {
            console.log("Unable to get start index:", startIndex);
        }
    } catch (e) {
        // defensive: if anything goes wrong, don't block the rest of the UI
        console.error('insertNegative: error while removing next empty <p> element', e);
    }
}

function removeSample( targetItem ) {

    console.log("Removing: " + targetItem)
    const gridC = document.getElementById("plate-container");
    var existing_wells = document.getElementsByClassName("well");
    var en_num = existing_wells.length + 1;
    var well_name = "blank_" + en_num;
    var elem = document.createElement("div");
    elem.setAttribute("id", well_name);
    elem.setAttribute("class", "well");
    elem.setAttribute("draggable", "true");
    elem.innerHTML = '<p style="font-size: 0.7em; text-align: center; word-wrap: break-word;"></p>'
    gridC.insertBefore(elem, targetItem);
    // targetItem.remove();
    try {
        const children = Array.from(gridC.children);
        // find the index where the new element currently sits
        const childIndex = children.indexOf(targetItem);
        if (childIndex !== -1) {
            console.log("Removing from index: " + childIndex);
            gridC.removeChild(children[childIndex]);
        }
    } catch (e) {
        // defensive: if anything goes wrong, don't block the rest of the UI
        console.error('removeSample: error while removing next empty <p> element', e);
    }
    // gridC.remove(targetItem);
}





/**
* Run the app.
*/
init();


