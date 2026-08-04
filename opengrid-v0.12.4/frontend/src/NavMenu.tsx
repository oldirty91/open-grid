import {useEffect,useRef,useState} from "react";

export default function NavMenu({active}:{active:"map"|"plugins"|"artifacts"}){
 const[open,setOpen]=useState(false);
 const root=useRef<HTMLDivElement>(null);
 useEffect(()=>{
  const close=(event:MouseEvent)=>{
   if(root.current&&!root.current.contains(event.target as Node))setOpen(false);
  };
  document.addEventListener("mousedown",close);
  return()=>document.removeEventListener("mousedown",close);
 },[]);
 return <div className="navMenu" ref={root}>
  <button className="navMenuButton" onClick={()=>setOpen(!open)} aria-label="Open navigation menu">
   <span className="hamburger">☰</span><span>OpenGrid</span>
  </button>
  {open&&<div className="navDropdown">
   <a className={active==="map"?"active":""} href="/">Map</a>
   <a className={active==="plugins"?"active":""} href="/plugins">Plugins</a>
   <a className={active==="artifacts"?"active":""} href="/artifacts">Artifacts</a>
  </div>}
 </div>
}
