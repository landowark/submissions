//function openMulti() {
//  if (document.querySelector(".selectWrapper").style.pointerEvents == "all") {
//    document.querySelector(".selectWrapper").style.opacity = 0;
//    document.querySelector(".selectWrapper").style.pointerEvents = "none";
//    resetAllMenus();
//  } else {
//    document.querySelector(".selectWrapper").style.opacity = 1;
//    document.querySelector(".selectWrapper").style.pointerEvents = "all";
//  }
//}
//function nextMenu(e) {
//  menuIndex = eval(event.target.parentNode.id.slice(-1));
//  document.querySelectorAll(".multiSelect")[menuIndex].style.transform =
//    "translateX(-100%)";
//  // document.querySelectorAll(".multiSelect")[menuIndex].style.clipPath = "polygon(0 0, 0 0, 0 100%, 0% 100%)";
//  document.querySelectorAll(".multiSelect")[menuIndex].style.clipPath =
//    "polygon(100% 0, 100% 0, 100% 100%, 100% 100%)";
//  document.querySelectorAll(".multiSelect")[menuIndex + 1].style.transform =
//    "translateX(0)";
//  document.querySelectorAll(".multiSelect")[menuIndex + 1].style.clipPath =
//    "polygon(0 0, 100% 0, 100% 100%, 0% 100%)";
//}
//function prevMenu(e) {
//  menuIndex = eval(event.target.parentNode.id.slice(-1));
//  document.querySelectorAll(".multiSelect")[menuIndex].style.transform =
//    "translateX(100%)";
//  document.querySelectorAll(".multiSelect")[menuIndex].style.clipPath =
//    "polygon(0 0, 0 0, 0 100%, 0% 100%)";
//  document.querySelectorAll(".multiSelect")[menuIndex - 1].style.transform =
//    "translateX(0)";
//  document.querySelectorAll(".multiSelect")[menuIndex - 1].style.clipPath =
//    "polygon(0 0, 100% 0, 100% 100%, 0% 100%)";
//}
//function resetAllMenus() {
//  setTimeout(function () {
//    var x = document.getElementsByClassName("multiSelect");
//    var i;
//    for (i = 1; i < x.length; i++) {
//      x[i].style.transform = "translateX(100%)";
//      x[i].style.clipPath = "polygon(0 0, 0 0, 0 100%, 0% 100%)";
//    }
//    document.querySelectorAll(".multiSelect")[0].style.transform =
//      "translateX(0)";
//    document.querySelectorAll(".multiSelect")[0].style.clipPath =
//      "polygon(0 0, 100% 0, 100% 100%, 0% 100%)";
//  }, 300);
//}


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
    const task_id = taskItemInContext.getAttribute("id")
    backend.log("Task action - " + link.getAttribute("data-action"))
    switch (link.getAttribute("data-action")) {
        case "InsertSample":
            insertSample(contextIndex, task_id);
        break;
        case "InsertControl":
            insertControl(contextIndex);
        break;
        case "RemoveSample":
            removeSample(contextIndex);
        break;
        default:
            backend.log("default");
        break;
    }
    toggleMenuOff();
}

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
var menuHeader = document.getElementById("menu-header");
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

function insertControl( index ) {
    backend.log( "Index - " + index + ", InsertEN");
    var existing_ens = document.getElementsByClassName("EN");
    backend.log(existing_ens.length);
}

function removeSample( index ) {
    backend.log( "Index - " + index + ", RemoveSample");
}


/**
* Run the app.
*/
init();


