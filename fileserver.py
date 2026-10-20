#!/usr/bin/env python3
"""FileSpace: a single-file, styled, read-only file browser for Windows.

Run:
    python fileserver.py
Optional:
    python fileserver.py --root D:\\ --host 0.0.0.0 --port 6789 --env .env

Settings live in a ".env" file next to this script (created on first run):

    FILESPACE_ROOT=D:\\
    FILESPACE_CREATE_SHORTCUT=false
    FILESPACE_EMAIL=you@example.com
    FILESPACE_PASSWORD=your-long-password
    FILESPACE_ALLOWED_IPS=203.0.113.7, 100.101.102.103
    FILESPACE_PUBLIC=false

The .env file is re-read automatically when it changes, so you can edit the
allowed IPs or flip FILESPACE_PUBLIC without restarting the server.

Preview: images, videos, audio, PDFs and text files open in an in-page viewer.
The FileSpace folder itself (this script, .env, logs) is never shared.
You are signed out automatically after 5 minutes of inactivity.

Security: plain HTTP does not encrypt the password or the files in transit.
Prefer a VPN such as Tailscale, or only use this on networks you trust.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import io
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from collections import OrderedDict, deque
from dataclasses import dataclass
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

try:  # optional: faster, smaller thumbnails (pip install pillow)
    from PIL import Image, ImageOps
    HAVE_PIL = True
except Exception:  # pragma: no cover
    HAVE_PIL = False

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>FileSpace</title>
<style>
:root{--bg:#0b1120;--panel:#121b30;--panel2:#18233c;--line:#26334f;--text:#eef2ff;--muted:#94a3c2;--accent:#8ea2ff;--ok:#34d399;--warn:#fbbf24;--bad:#f87171}
*{box-sizing:border-box}html,body{margin:0}
[hidden]{display:none!important}
body{min-height:100vh;color:var(--text);font:14px/1.45 Inter,system-ui,-apple-system,"Segoe UI",sans-serif;background:radial-gradient(ellipse at 8% -5%,#1e2a58 0,transparent 38%),radial-gradient(ellipse at 100% 0,#0e3347 0,transparent 30%),var(--bg)}
body.lock{overflow:hidden}
button,input,select{font:inherit;color:inherit}button{cursor:pointer}a{color:inherit;text-decoration:none}
.wrap{max-width:1160px;margin:0 auto;padding:16px 16px 60px}
.top{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:16px}
.brand{display:flex;align-items:center;gap:10px;font-weight:800;font-size:18px;letter-spacing:-.03em}
.logo{width:36px;height:36px;border-radius:11px;display:grid;place-items:center;background:linear-gradient(135deg,#a5b4fc,#67e8f9);color:#0b1120;font-size:19px}
.right{display:flex;align-items:center;gap:8px;position:relative}
.btn{background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:8px 12px;font-size:12px;font-weight:600;display:inline-flex;align-items:center;gap:6px}
.btn:hover{border-color:var(--accent)}.btn.primary{background:linear-gradient(135deg,#a5b4fc,#67e8f9);color:#0b1120;border:0}
.pill{display:inline-flex;align-items:center;gap:7px;border-radius:999px;padding:7px 12px;font-size:12px;font-weight:600;background:var(--panel2);border:1px solid var(--line)}
.dot{width:8px;height:8px;border-radius:50%;background:var(--muted);display:inline-block;flex:0 0 8px}
.dot.ok,.pill.ok .dot{background:var(--ok);box-shadow:0 0 0 3px #34d39922}.dot.warn,.pill.warn .dot{background:var(--warn);box-shadow:0 0 0 3px #fbbf2422}.dot.bad,.pill.bad .dot{background:var(--bad);box-shadow:0 0 0 3px #f8717122}
.pill.ok{border-color:#245a47}.pill.warn{border-color:#6b5a1e}.pill.bad{border-color:#6b2a2a}
.pop{position:absolute;right:0;top:44px;width:min(340px,calc(100vw - 32px));z-index:40;background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:6px;box-shadow:0 20px 50px #0007}
.hhead{display:flex;justify-content:space-between;padding:10px 10px 6px;font-size:12px;color:var(--muted)}.hhead b{color:var(--text)}
.hrow{display:flex;gap:10px;padding:8px 10px;align-items:flex-start}.hrow .dot{margin-top:6px}.hrow b{font-size:12px}
.hfoot{padding:8px 10px 10px;color:var(--muted);font-size:11px;border-top:1px solid var(--line);margin-top:4px}
.search{display:flex;align-items:center;gap:10px;background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:0 14px;height:52px}
.search:focus-within{border-color:var(--accent);box-shadow:0 0 0 3px #8ea2ff22}
.search svg{flex:0 0 18px;color:var(--muted)}
.search input{flex:1;min-width:0;background:none;border:0;outline:none;font-size:15px}
.search input::placeholder{color:#667797}
.x{background:none;border:0;color:var(--muted);font-size:18px;padding:4px 6px}
kbd{border:1px solid var(--line);border-radius:6px;padding:1px 6px;font-size:11px;color:var(--muted)}
.bar{display:flex;align-items:center;gap:10px;margin:14px 0 6px;flex-wrap:wrap}
.crumbs{display:flex;align-items:center;gap:4px;flex:1;min-width:200px;flex-wrap:wrap}
.crumbs button{background:none;border:0;color:var(--accent);padding:4px 6px;border-radius:8px;font-weight:650;font-size:13px}
.crumbs button:hover{background:#8ea2ff14}.crumbs button.cur{color:var(--text)}.sep{color:#556485}
.tools{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.chips{display:flex;gap:6px;overflow-x:auto;max-width:100%;scrollbar-width:none}
.chip{background:none;border:1px solid var(--line);border-radius:999px;padding:6px 12px;font-size:12px;color:var(--muted);white-space:nowrap}
.chip.on{background:#8ea2ff1f;border-color:var(--accent);color:var(--text)}
select.btn{padding-right:6px;appearance:auto}select.btn option{background:#18233c}
.seg{display:flex;border:1px solid var(--line);border-radius:10px;overflow:hidden}
.seg button{background:var(--panel2);border:0;padding:8px 10px;font-size:12px;color:var(--muted)}.seg button.on{background:#8ea2ff26;color:var(--text)}
.status{color:var(--muted);font-size:12px;margin:2px 4px 12px;min-height:18px}
.list{background:var(--panel);border:1px solid var(--line);border-radius:18px;overflow:hidden}
.lhead,.row{display:grid;grid-template-columns:minmax(0,1fr) 84px 170px 76px 40px;gap:12px;align-items:center;padding:0 14px}
.lhead{height:36px;color:#6f7fa0;font-size:10px;text-transform:uppercase;letter-spacing:.1em}
.row{padding:9px 14px;border-top:1px solid var(--line);cursor:pointer;outline:none}
.row:hover,.row:focus-visible{background:#8ea2ff12}
.main{display:flex;align-items:center;gap:12px;min-width:0}.info{min-width:0}
.name{font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sub{font-size:11px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.c{color:var(--muted);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.act{text-align:right}.chev{color:#6f7fa0;font-size:20px}
.dl{display:inline-grid;place-items:center;width:32px;height:32px;border-radius:9px;color:var(--muted);border:1px solid transparent}
.dl:hover{border-color:var(--accent);color:var(--text)}
.gof{background:none;border:0;color:var(--accent);font-size:11px;padding:0 4px}.gof:hover{text-decoration:underline}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:14px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:10px;cursor:pointer;outline:none;min-width:0}
.card:hover,.card:focus-visible{border-color:var(--accent)}
.cname{margin-top:8px;font-weight:650;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.csub{font-size:11px;color:var(--muted)}
.tile{position:relative;flex:0 0 42px;width:42px;height:42px;border-radius:11px;display:grid;place-items:center;overflow:hidden;background:#222e49;color:#9fb0d0;font-size:10px;font-weight:800;letter-spacing:.04em}
.tile img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}.tile img+b{display:none}
.tile.big{width:100%;height:auto;flex:none;aspect-ratio:4/3;border-radius:12px;font-size:18px}
.tile svg{width:52%;height:52%}
.tile.folder{background:#3b3119;color:#fbbf24}.k-image{background:#173a3a;color:#5eead4}.k-video{background:#35294d;color:#c4b5fd}.k-audio{background:#40301b;color:#fbbf24}.k-pdf{background:#4a2328;color:#fca5a5}.k-text{background:#1d3252;color:#93c5fd}.k-doc{background:#1d3550;color:#7dd3fc}.k-archive{background:#3a3a22;color:#fde68a}
.empty{padding:56px 20px;text-align:center;color:var(--muted)}.empty.err{color:#fca5a5}
.offline{position:sticky;top:0;z-index:60;background:#4a1d1d;color:#fecaca;text-align:center;padding:8px;font-size:12px}
.toast{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);z-index:80;background:#2b2412;border:1px solid #6b5a1e;color:#fde68a;padding:10px 14px;border-radius:14px;display:flex;gap:12px;align-items:center;box-shadow:0 14px 40px #0008;max-width:calc(100vw - 24px)}
.toast .btn{background:#4a3d14;border-color:#8a7424;color:#fff}
.viewer{position:fixed;inset:0;z-index:50;display:flex;flex-direction:column;background:rgba(6,9,18,.97)}
.vhead{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 14px;border-bottom:1px solid var(--line)}
.vtitle{min-width:0}.vtitle b{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.vtitle span{color:var(--muted);font-size:11px}
.vact{display:flex;gap:8px;flex:0 0 auto}
.vbody{flex:1;min-height:0;display:flex;align-items:center;justify-content:center;padding:14px;overflow:auto}
.vbody img.pv{max-width:100%;max-height:100%;object-fit:contain;cursor:zoom-in;border-radius:8px}
.vbody.zoom{align-items:flex-start;justify-content:flex-start}.vbody.zoom img.pv{max-width:none;max-height:none;cursor:zoom-out}
.vbody video{max-width:100%;max-height:100%;border-radius:10px;background:#000;outline:none}
.vbody iframe{width:100%;height:100%;border:0;border-radius:10px;background:#fff}
.vbody.k-text{align-items:stretch;justify-content:stretch;background:none;color:inherit}
.vbody pre{margin:0;width:100%;overflow:auto;background:#0a0f1d;border:1px solid var(--line);border-radius:12px;padding:16px;font:12.5px/1.55 ui-monospace,Consolas,"Cascadia Mono",monospace;white-space:pre-wrap;word-break:break-word;color:#dbe4ff}
.vbody .tn{margin-top:10px;text-align:center;color:var(--muted);font-size:11px}
.textwrap{width:100%;height:100%;display:flex;flex-direction:column;min-height:0}.textwrap pre{flex:1}
.nopreview,.audiocard{max-width:380px;width:100%;text-align:center;display:flex;flex-direction:column;align-items:center;gap:14px;color:var(--muted)}
.nopreview .tile,.audiocard .tile{width:130px;height:130px;aspect-ratio:auto;font-size:22px}
.audiocard audio{width:100%}.audiocard b{color:var(--text)}
.loading{color:var(--muted)}
.nav{position:absolute;top:50%;transform:translateY(-50%);width:44px;height:64px;border:1px solid var(--line);background:#121b30cc;border-radius:12px;font-size:26px;display:grid;place-items:center;z-index:2}
.nav:hover{border-color:var(--accent)}.nav.prev{left:10px}.nav.next{right:10px}
.vpos{position:absolute;bottom:10px;left:50%;transform:translateX(-50%);font-size:11px;color:var(--muted);background:#0b1120cc;border-radius:999px;padding:3px 10px;z-index:2}
@media(max-width:760px){.wrap{padding:12px 10px 50px}.lhead{display:none}.row{grid-template-columns:minmax(0,1fr) auto 36px;gap:8px}.row .c:nth-of-type(1),.row .c:nth-of-type(2){display:none}.nav{width:36px;height:52px}.grid{grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:10px}kbd{display:none}.vbody{padding:8px}}
</style></head>
<body>
<div class="offline" id="offline" hidden>Can't reach the server. Retrying…</div>
<div class="wrap">
<header class="top">
  <div class="brand"><span class="logo">▱</span>FileSpace</div>
  <div class="right">
    <button class="pill" id="health" type="button" aria-haspopup="true"><i class="dot"></i><span id="healthTxt">Checking…</span></button>
    <button class="btn" id="logout" type="button">Log out</button>
    <div class="pop" id="hpop" hidden></div>
  </div>
</header>

<label class="search">
  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
  <input id="q" type="search" placeholder="Search in this folder and everything inside it…" autocomplete="off" spellcheck="false">
  <button class="x" id="clearQ" type="button" hidden aria-label="Clear search">✕</button><kbd>/</kbd>
</label>

<div class="bar">
  <button class="btn" id="up" type="button" title="Parent folder">↑</button>
  <nav class="crumbs" id="crumbs" aria-label="Breadcrumb"></nav>
  <div class="tools">
    <div class="chips" id="chips"></div>
    <select class="btn" id="sort" aria-label="Sort by"><option value="name">Name</option><option value="new">Newest first</option><option value="old">Oldest first</option><option value="big">Largest first</option></select>
    <div class="seg"><button id="vList" type="button" title="List view">☰</button><button id="vGrid" type="button" title="Grid view">▦</button></div>
  </div>
</div>
<div class="status" id="status"></div>
<div id="content"></div>
</div>

<div class="viewer" id="viewer" hidden role="dialog" aria-modal="true" aria-label="File preview">
  <div class="vhead">
    <div class="vtitle"><b id="vname"></b><span id="vmeta"></span></div>
    <div class="vact"><a class="btn" id="vopen" target="_blank" rel="noopener" hidden>Open in new tab</a><a class="btn primary" id="vdl">Download</a><button class="btn" id="vclose" type="button" aria-label="Close preview">✕ Close</button></div>
  </div>
  <div class="vbody" id="vbody"></div>
  <button class="nav prev" id="vprev" type="button" aria-label="Previous file">‹</button>
  <button class="nav next" id="vnext" type="button" aria-label="Next file">›</button>
  <div class="vpos" id="vpos"></div>
</div>

<div class="toast" id="idle" hidden><span>No activity — signing you out in <b id="idleT">1:00</b></span><button class="btn" id="stay" type="button">Stay signed in</button></div>

<script>
/*__BOOT__*/
const $=(s,r=document)=>r.querySelector(s);
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const enc=encodeURIComponent;
const pstore={get(k,d){try{return localStorage.getItem(k)||d}catch{return d}},set(k,v){try{localStorage.setItem(k,v)}catch{}}};
const KIND={image:'Image',video:'Video',audio:'Audio',pdf:'PDF document',text:'Text file',doc:'Document',archive:'Archive',other:'File',folder:'Folder'};
const FILTERS=[['all','All'],['image','Images'],['video','Videos'],['audio','Audio'],['docs','Documents']];
const FOLDER='<svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 6.5A2.5 2.5 0 0 1 5.5 4h3.9c.6 0 1.2.3 1.6.8L12 6h6.5A2.5 2.5 0 0 1 21 8.5v9a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 17.5z"/></svg>';
const st={path:'',entries:[],thumbs:false,searching:false,truncated:false,q:'',filter:'all',sort:pstore.get('fsSort','name'),view:pstore.get('fsView','list')};
let shown=[],loadSeq=0,searchTimer=null,leaving=false;

function fmtSize(n){if(n==null)return '';if(n<1024)return n+' B';const u=['KB','MB','GB','TB'];let i=-1;do{n/=1024;i++}while(n>=1024&&i<u.length-1);return n.toFixed(n>=10?0:1)+' '+u[i]}
function fmtDate(s){if(!s)return '';const d=new Date(s*1000);return d.toLocaleDateString(undefined,{day:'numeric',month:'short',year:'numeric'})+', '+d.toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit'})}
function fmtClock(sec){sec=Math.max(0,Math.ceil(sec));return Math.floor(sec/60)+':'+String(sec%60).padStart(2,'0')}
function fmtUp(s){if(s<60)return s+'s';if(s<3600)return Math.floor(s/60)+'m';if(s<86400)return Math.floor(s/3600)+'h '+Math.floor(s%3600/60)+'m';return Math.floor(s/86400)+'d '+Math.floor(s%86400/3600)+'h'}
const parentOf=p=>{const i=p.lastIndexOf('/');return i<0?'':p.slice(0,i)};
const fileUrl=e=>(e.kind==='video'&&/\.mkv$/i.test(e.name)?'/api/playback':'/api/file')+'?path='+enc(e.relative_path);
const dlUrl=e=>'/api/download?path='+enc(e.relative_path);

function signedOut(){if(leaving)return;leaving=true;try{sessionStorage.setItem('fs_out','1')}catch{}fetch('/logout?reason=idle',{method:'POST'}).catch(()=>{}).finally(()=>location.reload())}
async function api(url){const r=await fetch(url,{cache:'no-store'});if(r.status===401){signedOut();throw Error('Signed out')}const d=await r.json().catch(()=>({error:'Invalid server response'}));if(!r.ok)throw Error(d.error||('Request failed ('+r.status+')'));return d}

/* ---------- navigation ---------- */
function pathFromHash(){try{return location.hash.replace(/^#\/?/,'').split('/').filter(Boolean).map(decodeURIComponent).join('/')}catch{return ''}}
function go(path){const h='#/'+path.split('/').filter(Boolean).map(enc).join('/');if(location.hash===h||(h==='#/'&&!location.hash))loadDir(path);else location.hash=h}
function crumbs(){const parts=st.path.split('/').filter(Boolean);let h=`<button data-p="" class="${parts.length?'':'cur'}">${esc(BOOT.root)}</button>`,acc='';parts.forEach((p,i)=>{acc=acc?acc+'/'+p:p;h+=`<span class="sep">›</span><button data-p="${esc(acc)}" class="${i===parts.length-1?'cur':''}">${esc(p)}</button>`});$('#crumbs').innerHTML=h}
$('#crumbs').onclick=e=>{const b=e.target.closest('button');if(b)go(b.dataset.p)};
$('#up').onclick=()=>{const p=st.path.split('/').filter(Boolean);p.pop();go(p.join('/'))};
window.addEventListener('hashchange',()=>loadDir(pathFromHash()));

async function loadDir(path){const seq=++loadSeq;st.path=path;st.searching=false;st.q='';$('#q').value='';$('#clearQ').hidden=true;crumbs();$('#status').textContent='Loading…';
 try{const d=await api('/api/list?path='+enc(path));if(seq!==loadSeq)return;st.entries=d.entries||[];st.thumbs=!!d.thumbs;render()}
 catch(e){if(seq!==loadSeq)return;st.entries=[];shown=[];$('#content').className='';$('#content').innerHTML=`<div class="empty err">${esc(e.message)}</div>`;$('#status').textContent=''}}
async function runSearch(q){const seq=++loadSeq;$('#status').textContent='Searching…';
 try{const d=await api('/api/search?path='+enc(st.path)+'&q='+enc(q));if(seq!==loadSeq)return;st.entries=d.entries||[];st.thumbs=!!d.thumbs;st.truncated=!!d.truncated;st.searching=true;render()}
 catch(e){if(seq!==loadSeq)return;$('#content').className='';$('#content').innerHTML=`<div class="empty err">${esc(e.message)}</div>`;$('#status').textContent=''}}
$('#q').addEventListener('input',()=>{clearTimeout(searchTimer);const q=$('#q').value.trim();$('#clearQ').hidden=!q;
 searchTimer=setTimeout(()=>{if(!q){if(st.searching)loadDir(st.path);st.q='';return}if(q.length<2)return;st.q=q;runSearch(q)},250)});
$('#clearQ').onclick=()=>{$('#q').value='';$('#clearQ').hidden=true;const was=st.searching;st.q='';if(was)loadDir(st.path);$('#q').focus()};

/* ---------- list / grid ---------- */
function matchFilter(e){const f=st.filter;if(e.is_dir)return f==='all'||!st.searching;if(f==='all')return true;if(f==='docs')return ['pdf','text','doc'].includes(e.kind);return e.kind===f}
const cmpName=(a,b)=>a.name.localeCompare(b.name,undefined,{numeric:true,sensitivity:'base'});
function compute(){const by={name:cmpName,new:(a,b)=>b.modified-a.modified,old:(a,b)=>a.modified-b.modified,big:(a,b)=>(b.size||0)-(a.size||0)}[st.sort]||cmpName;
 shown=st.entries.filter(matchFilter).sort((a,b)=>Number(b.is_dir)-Number(a.is_dir)||by(a,b)||cmpName(a,b))}
function thumbUrl(e){if(e.kind!=='image')return null;if(st.thumbs&&!/\.svg$/i.test(e.name))return '/api/thumb?path='+enc(e.relative_path);if(e.size!=null&&e.size<=1500000)return fileUrl(e);return null}
function tile(e,big){if(e.is_dir)return `<span class="tile folder${big?' big':''}">${FOLDER}</span>`;const t=thumbUrl(e);return `<span class="tile k-${e.kind}${big?' big':''}">${t?`<img loading="lazy" decoding="async" alt="" src="${t}" onerror="this.remove()">`:''}<b>${esc((e.extension||'FILE').slice(0,4))}</b></span>`}
function row(e,i){const par=parentOf(e.relative_path);const sub=st.searching?`in ${esc('/'+par)} <button class="gof" type="button" data-f="${esc(par)}">Open folder</button>`:esc(KIND[e.kind]||'File');
 return `<div class="row" data-i="${i}" tabindex="0" role="button"><div class="main">${tile(e)}<div class="info"><div class="name" title="${esc(e.name)}">${esc(e.name)}</div><div class="sub">${sub}</div></div></div><div class="c">${esc(e.is_dir?'Folder':(e.extension||'File'))}</div><div class="c">${fmtDate(e.modified)}</div><div class="c">${e.is_dir?'':fmtSize(e.size)}</div><div class="act">${e.is_dir?'<span class="chev">›</span>':`<a class="dl" href="${dlUrl(e)}" title="Download" aria-label="Download ${esc(e.name)}">⬇</a>`}</div></div>`}
function card(e,i){return `<div class="card" data-i="${i}" tabindex="0" role="button">${tile(e,true)}<div class="cname" title="${esc(e.name)}">${esc(e.name)}</div><div class="csub">${e.is_dir?'Folder':fmtSize(e.size)}</div></div>`}
function statusText(){const n=shown.length;if(st.searching)return `${n} result${n===1?'':'s'} for “${st.q}” in ${st.path?'/'+st.path:BOOT.root}${st.truncated?' — showing the first matches only':''}`;return `${n} item${n===1?'':'s'}`}
function render(){compute();$('#status').textContent=statusText();const c=$('#content');
 if(!shown.length){c.className='';c.innerHTML=`<div class="empty">${st.searching?'No matches found.':(st.entries.length?'Nothing matches this filter.':'This folder is empty.')}</div>`;return}
 if(st.view==='grid'){c.className='grid';c.innerHTML=shown.map(card).join('')}
 else{c.className='list';c.innerHTML='<div class="lhead"><span>Name</span><span>Type</span><span>Modified</span><span>Size</span><span></span></div>'+shown.map(row).join('')}}
function activate(i){const e=shown[i];if(!e)return;if(e.is_dir)go(e.relative_path);else openViewer(e)}
$('#content').addEventListener('click',ev=>{if(ev.target.closest('.dl'))return;const g=ev.target.closest('.gof');if(g){ev.stopPropagation();go(g.dataset.f);return}const el=ev.target.closest('[data-i]');if(el)activate(+el.dataset.i)});

/* chips / sort / view */
$('#chips').innerHTML=FILTERS.map(([k,l])=>`<button class="chip${k===st.filter?' on':''}" data-k="${k}" type="button">${l}</button>`).join('');
$('#chips').onclick=e=>{const b=e.target.closest('.chip');if(!b)return;st.filter=b.dataset.k;document.querySelectorAll('.chip').forEach(x=>x.classList.toggle('on',x===b));render()};
$('#sort').value=st.sort;$('#sort').onchange=()=>{st.sort=$('#sort').value;pstore.set('fsSort',st.sort);render()};
function setView(v){st.view=v;pstore.set('fsView',v);$('#vList').classList.toggle('on',v==='list');$('#vGrid').classList.toggle('on',v==='grid');render()}
$('#vList').onclick=()=>setView('list');$('#vGrid').onclick=()=>setView('grid');

/* ---------- viewer ---------- */
const V=$('#viewer');let vItems=[],vPos=-1,vSeq=0,vOpen=false;
function openViewer(e){vItems=shown.filter(x=>!x.is_dir);vPos=vItems.indexOf(e);if(vPos<0)return;if(!vOpen){vOpen=true;history.pushState({v:1},'');document.body.classList.add('lock');V.hidden=false}showItem()}
function closeViewer(fromPop){if(!vOpen)return;vOpen=false;vSeq++;$('#vbody').innerHTML='';V.hidden=true;document.body.classList.remove('lock');if(!fromPop&&history.state&&history.state.v)history.back()}
window.addEventListener('popstate',()=>{if(vOpen)closeViewer(true)});
$('#vclose').onclick=()=>closeViewer();
function step(d){if(vItems.length<2)return;vPos=(vPos+d+vItems.length)%vItems.length;showItem()}
$('#vprev').onclick=()=>step(-1);$('#vnext').onclick=()=>step(1);
function preload(i){const x=vItems[i];if(x&&x.kind==='image'){new Image().src=fileUrl(x)}}
function nopreview(e,msg){return `<div class="nopreview">${tile(e,true)}<b style="color:var(--text)">${esc(e.name)}</b><p style="margin:0">${msg}</p><a class="btn primary" href="${dlUrl(e)}">Download</a></div>`}
async function loadText(e,body,seq){try{const r=await fetch(fileUrl(e),{headers:{Range:'bytes=0-262143'},cache:'no-store'});if(seq!==vSeq)return;if(r.status===401){signedOut();return}if(!r.ok)throw 0;const t=await r.text();if(seq!==vSeq)return;let total=null;const cr=r.headers.get('Content-Range');if(cr){const m=cr.match(/\/(\d+)$/);if(m)total=+m[1]}
 body.innerHTML='<div class="textwrap"><pre></pre></div>';$('pre',body).textContent=t||'(empty file)';if(total&&total>262144){const n=document.createElement('div');n.className='tn';n.textContent='Showing the first 256 KB of '+fmtSize(total)+'. Download the file to see everything.';$('.textwrap',body).appendChild(n)}}
 catch{if(seq===vSeq)body.innerHTML=nopreview(e,'This file could not be loaded.')}}
function showItem(){const e=vItems[vPos],seq=++vSeq,body=$('#vbody');
 $('#vname').textContent=e.name;$('#vmeta').textContent=[KIND[e.kind]||'File',fmtSize(e.size),fmtDate(e.modified)].filter(Boolean).join(' · ');
 $('#vdl').href=dlUrl(e);const can=['image','video','audio','pdf','text'].includes(e.kind);$('#vopen').hidden=!can;$('#vopen').href=fileUrl(e);
 $('#vpos').textContent=vItems.length>1?(vPos+1)+' / '+vItems.length:'';$('#vprev').hidden=$('#vnext').hidden=vItems.length<2;
 body.innerHTML='';body.className='vbody k-'+e.kind;
 if(e.kind==='image'){const im=new Image();im.className='pv';im.alt=e.name;im.onerror=()=>{if(seq===vSeq)body.innerHTML=nopreview(e,'This image could not be displayed.')};im.onclick=()=>body.classList.toggle('zoom');im.src=fileUrl(e);body.appendChild(im);preload(vPos+1);preload(vPos-1)}
 else if(e.kind==='video'){const v=document.createElement('video');v.controls=true;v.autoplay=true;v.playsInline=true;v.preload='metadata';v.onerror=()=>{if(seq===vSeq)body.innerHTML=nopreview(e,'The server could not prepare browser playback. Check Server health and its FFmpeg setup.')};v.src=fileUrl(e);body.appendChild(v)}
 else if(e.kind==='audio'){body.innerHTML=`<div class="audiocard">${tile(e,true)}<b>${esc(e.name)}</b></div>`;const a=document.createElement('audio');a.controls=true;a.autoplay=true;a.onerror=()=>{if(seq===vSeq)body.innerHTML=nopreview(e,'Your browser can’t play this audio format.')};a.src=fileUrl(e);$('.audiocard',body).appendChild(a)}
 else if(e.kind==='pdf'){const f=document.createElement('iframe');f.title=e.name;f.src=fileUrl(e);body.appendChild(f)}
 else if(e.kind==='text'){body.innerHTML='<div class="loading">Loading…</div>';loadText(e,body,seq)}
 else body.innerHTML=nopreview(e,'No preview is available for this file type.')}
let tx=null;V.addEventListener('touchstart',e=>{tx=e.touches.length===1?e.touches[0].clientX:null},{passive:true});
V.addEventListener('touchend',e=>{if(tx==null||e.target.closest('video,audio,iframe,pre'))return;const dx=e.changedTouches[0].clientX-tx;tx=null;if(Math.abs(dx)>70)step(dx<0?1:-1)},{passive:true});

/* ---------- keyboard ---------- */
addEventListener('keydown',e=>{const tag=e.target.tagName||'';const typing=/INPUT|SELECT|TEXTAREA/.test(tag);
 if(e.key==='Escape'){if(!$('#hpop').hidden){$('#hpop').hidden=true;return}if(vOpen){closeViewer();return}if($('#q').value){$('#clearQ').click();return}return}
 if(vOpen){if(!typing&&!/VIDEO|AUDIO/.test(tag)){if(e.key==='ArrowRight')step(1);else if(e.key==='ArrowLeft')step(-1)}return}
 if(e.key==='/'&&!typing){e.preventDefault();$('#q').focus();return}
 if((e.key==='Enter'||e.key===' ')&&e.target.matches&&e.target.matches('[data-i]')){e.preventDefault();activate(+e.target.dataset.i)}});

/* ---------- health + automatic sign-out ---------- */
let deadline=Date.now()+BOOT.idle*1000,lastPing=0,lastHealth=null,fails=0,confirming=false;
const setDeadline=sec=>{deadline=Date.now()+sec*1000};
function setPill(kind){const p=$('#health');const m={ok:['Online','ok'],warn:['Attention','warn'],fail:['Problem','bad'],slow:['Slow','warn'],down:['Offline','bad']}[kind]||['Online','ok'];p.className='pill '+m[1];$('#healthTxt').textContent=m[0]}
function renderPop(){const d=lastHealth,el=$('#hpop');if(!d){el.innerHTML='<div class="hrow">Checking…</div>';return}
 el.innerHTML=`<div class="hhead"><b>Server health</b><span>Up ${fmtUp(d.uptime)}</span></div>`+d.checks.map(c=>`<div class="hrow"><i class="dot ${c.status==='ok'?'ok':c.status==='warn'?'warn':'bad'}"></i><div><b>${esc(c.name)}</b><div class="sub">${esc(c.detail)}</div></div></div>`).join('')+`<div class="hfoot">You’re signed out automatically after ${Math.round(BOOT.idle/60)} minutes of inactivity.</div>`}
$('#health').onclick=e=>{e.stopPropagation();const p=$('#hpop');p.hidden=!p.hidden;if(!p.hidden)renderPop()};
document.addEventListener('click',e=>{if(!e.target.closest('#hpop,#health'))$('#hpop').hidden=true});
async function poll(){const t0=performance.now(),ac=new AbortController(),to=setTimeout(()=>ac.abort(),6000);
 try{const r=await fetch('/api/health',{cache:'no-store',signal:ac.signal});clearTimeout(to);if(r.status===401){signedOut();return}
  const d=await r.json(),ms=performance.now()-t0;fails=0;$('#offline').hidden=true;lastHealth=d;setDeadline(d.idle_left);setPill(ms>2500?'slow':d.status);if(!$('#hpop').hidden)renderPop()}
 catch{clearTimeout(to);if(++fails>=2){setPill('down');$('#offline').hidden=false}}}
async function ping(){lastPing=Date.now();try{const r=await fetch('/api/keepalive',{cache:'no-store'});if(r.status===401){signedOut();return}const d=await r.json();setDeadline(d.idle_left);$('#idle').hidden=true}catch{}}
function activity(){if(Date.now()-lastPing>15000)ping()}
['pointerdown','keydown','wheel','touchstart','mousemove','scroll'].forEach(ev=>addEventListener(ev,activity,{passive:true,capture:true}));
$('#stay').onclick=()=>ping();
setInterval(()=>{const m=document.querySelector('#viewer video,#viewer audio');if(m&&!m.paused&&Date.now()-lastPing>30000)ping()},5000);
setInterval(()=>{const left=(deadline-Date.now())/1000,t=$('#idle');if(left>0&&left<=60){t.hidden=false;$('#idleT').textContent=fmtClock(left)}else t.hidden=true;if(left<=0&&!confirming){confirming=true;poll().finally(()=>{confirming=false})}},1000);
setInterval(poll,10000);
$('#logout').onclick=()=>{fetch('/logout',{method:'POST'}).catch(()=>{}).finally(()=>location.reload())};

setView(st.view);poll();loadDir(pathFromHash());
</script></body></html>"""

LOGIN_PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>FileSpace · Sign in</title>
<style>
:root{--bg:#0a1020;--line:#26334b;--text:#edf2ff;--muted:#9ba9c2;--accent:#9ba9ff}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;padding:20px;background:radial-gradient(ellipse at 10% 0%,#202b55 0,transparent 35%),radial-gradient(ellipse at 95% 10%,#10334b 0,transparent 28%),var(--bg);color:var(--text);font:14px/1.5 Inter,system-ui,-apple-system,"Segoe UI",sans-serif}
.card{width:min(400px,100%);border:1px solid var(--line);border-radius:22px;background:rgba(17,26,45,.94);padding:30px;box-shadow:0 22px 65px #0004}
.brand{display:flex;align-items:center;gap:11px;font-size:19px;font-weight:800;letter-spacing:-.04em;margin-bottom:22px}.logo{width:42px;height:42px;border-radius:14px;display:grid;place-items:center;background:linear-gradient(135deg,#a5b4fc,#67e8f9);color:#0a1020;font-size:22px}
h1{font-size:26px;letter-spacing:-.04em;margin:0 0 6px}p{color:var(--muted);margin:0 0 22px}label{display:block;font-size:11px;color:var(--muted);margin:14px 0 6px;font-weight:600}
input{width:100%;border:1px solid #2b3852;background:#0c1527;border-radius:12px;padding:12px;color:var(--text);outline:none;font:inherit}input:focus{border-color:var(--accent);box-shadow:0 0 0 3px #9ba9ff20}
button{width:100%;margin-top:22px;border:0;border-radius:12px;padding:12px;font:inherit;font-weight:700;color:#0a1020;background:linear-gradient(135deg,#a5b4fc,#67e8f9);cursor:pointer}button:disabled{opacity:.6;cursor:wait}
.err{min-height:20px;margin-top:14px;color:#fca5a5;font-size:12px}.note{color:#fde68a;font-size:12px}
</style></head>
<body><form class="card" id="f" autocomplete="on">
<div class="brand"><span class="logo">▱</span>FileSpace</div>
<h1>Sign in</h1><p>Enter your credentials to browse files.</p>
<label for="email">Email</label><input id="email" name="email" type="email" autocomplete="username" required autofocus>
<label for="password">Password</label><input id="password" name="password" type="password" autocomplete="current-password" required>
<div class="err" id="err" role="alert"></div><div class="note" id="note"></div>
<button id="btn" type="submit">Sign in</button>
</form>
<script>
const f=document.getElementById('f'),err=document.getElementById('err'),btn=document.getElementById('btn');
try{if(sessionStorage.getItem('fs_out')){sessionStorage.removeItem('fs_out');document.getElementById('note').textContent='You were signed out. This happens automatically after 5 minutes of inactivity.'}}catch{}
f.addEventListener('submit',async e=>{e.preventDefault();err.textContent='';btn.disabled=true;
try{const r=await fetch('/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:f.email.value,password:f.password.value})});
const d=await r.json().catch(()=>({}));if(r.ok){location.reload();return}err.textContent=d.error||('Sign-in failed ('+r.status+')')}
catch{err.textContent='Could not reach the server.'}btn.disabled=false});
</script></body></html>"""

ENV_TEMPLATE = """# FileSpace settings. This file is re-read automatically when you save it,
# so you do not need to restart the server after editing.

# Folder or drive to share. A command-line --root overrides this value.
FILESPACE_ROOT=D:\
# Create or update "File Server.lnk" on the current user's Desktop.
FILESPACE_CREATE_SHORTCUT=false

# Login credentials
FILESPACE_EMAIL=you@example.com
FILESPACE_PASSWORD=change-this-long-password

# Devices allowed to connect: comma-separated IPs or ranges (CIDR).
# Example: FILESPACE_ALLOWED_IPS=203.0.113.7, 100.101.102.103, 192.168.1.0/24
# This PC (127.0.0.1) is always allowed.
FILESPACE_ALLOWED_IPS=

# false = only the IPs above can reach the site (everyone else gets "Access denied")
# true  = any device can reach the login page (login is still required)
FILESPACE_PUBLIC=false
"""

PLACEHOLDER_PASSWORD = "change-this-long-password"
PLACEHOLDER_EMAIL = "you@example.com"

SKIP_DIRS = {
    "$RECYCLE.BIN", "System Volume Information", "RECYCLER",
    "__pycache__", ".git", "node_modules",
}

COOKIE_NAME = "fs_session"
SESSION_IDLE_SECONDS = 5 * 60        # signed out after 5 minutes of inactivity
SESSION_MAX_SECONDS = 24 * 3600      # and always after 24 hours
MAX_LOGIN_FAILURES = 5               # per IP address
LOGIN_LOCK_SECONDS = 15 * 60
SEARCH_MAX_SCANNED = 15000
SEARCH_MAX_RESULTS = 500
CHUNK = 256 * 1024
LOG_MAX_BYTES = 5 * 1024 * 1024   # logs.txt is rotated to logs.old.txt above this size
TRUE_VALUES = {"1", "true", "yes", "on"}

CSP = ("default-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; "
       "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")


# --------------------------------------------------------------------------
# File types: what can be previewed in the browser (and how it is served)
# --------------------------------------------------------------------------
START_TIME = time.time()
INLINE_SVG_CSP = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
PREVIEW: dict[str, tuple[str, str]] = {}
for _ext, _mime in {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif",
                    "webp": "image/webp", "bmp": "image/bmp", "avif": "image/avif", "ico": "image/x-icon",
                    "svg": "image/svg+xml"}.items():
    PREVIEW[_ext] = ("image", _mime)
for _ext, _mime in {"mp4": "video/mp4", "m4v": "video/mp4", "webm": "video/webm", "ogv": "video/ogg",
                    "mov": "video/quicktime", "mkv": "video/x-matroska"}.items():
    PREVIEW[_ext] = ("video", _mime)
for _ext, _mime in {"mp3": "audio/mpeg", "wav": "audio/wav", "ogg": "audio/ogg", "oga": "audio/ogg",
                    "opus": "audio/ogg", "m4a": "audio/mp4", "aac": "audio/aac", "flac": "audio/flac"}.items():
    PREVIEW[_ext] = ("audio", _mime)
PREVIEW["pdf"] = ("pdf", "application/pdf")
for _ext in ("txt md markdown log csv tsv json xml yaml yml ini cfg conf toml py js mjs ts tsx jsx dart html htm "
             "css scss c h cpp hpp cs java kt go rs rb php sh bat cmd ps1 sql gradle properties srt vtt").split():
    PREVIEW[_ext] = ("text", "text/plain; charset=utf-8")
DOC_EXTS = set("doc docx xls xlsx ppt pptx rtf odt ods odp".split())
ARCHIVE_EXTS = set("zip rar 7z gz tar bz2 xz".split())
THUMB_EXTS = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}


def file_ext(name: str) -> str:
    return os.path.splitext(name)[1].lstrip(".").lower()


def kind_of(name: str) -> str:
    ext = file_ext(name)
    if ext in PREVIEW:
        return PREVIEW[ext][0]
    if ext in DOC_EXTS:
        return "doc"
    if ext in ARCHIVE_EXTS:
        return "archive"
    return "other"


def fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return str(n)


class ThumbCache:
    """Small in-memory cache of JPEG thumbnails (needs Pillow)."""

    def __init__(self, limit: int = 300):
        self.limit = limit
        self._d: OrderedDict = OrderedDict()
        self._lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(3)   # at most 3 thumbnails at once

    def get(self, path: Path, st: os.stat_result):
        if not HAVE_PIL:
            return None
        key = (str(path), st.st_mtime_ns, st.st_size)
        with self._lock:
            hit = self._d.get(key)
            if hit is not None:
                self._d.move_to_end(key)
                return hit
        with self._slots:
            data = self._make(path)
        if data:
            with self._lock:
                self._d[key] = data
                while len(self._d) > self.limit:
                    self._d.popitem(last=False)
        return data

    @staticmethod
    def _make(path: Path):
        try:
            with Image.open(path) as im:
                im = ImageOps.exif_transpose(im)
                im.thumbnail((360, 360))
                rgba = im.convert("RGBA")
                bg = Image.new("RGB", rgba.size, (24, 32, 52))
                bg.paste(rgba, mask=rgba.getchannel("A"))
                buf = io.BytesIO()
                bg.save(buf, "JPEG", quality=78)
                return buf.getvalue()
        except Exception:
            return None


# --------------------------------------------------------------------------
# Activity log (logs.txt) — one line per event, never contains passwords
# --------------------------------------------------------------------------
_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def clean(value, limit: int = 300) -> str:
    """Make user-controlled text safe for a one-line log entry."""
    text = _CTRL.sub(" ", str(value))
    return text if len(text) <= limit else text[:limit] + "..."


class ActivityLog:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.touch(exist_ok=True)
        except OSError as e:
            print(f"[warn] cannot create log file {path}: {e}", flush=True)

    def write(self, ip: str, event: str, detail: str = "") -> None:
        line = f"{datetime.now():%Y-%m-%d %H:%M:%S} | {ip:<15} | {event:<13} | {clean(detail)}\n"
        with self._lock:
            try:
                if self.path.exists() and self.path.stat().st_size > LOG_MAX_BYTES:
                    os.replace(self.path, self.path.with_name(self.path.stem + ".old" + self.path.suffix))
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write(line)
            except OSError:
                pass  # logging must never break the server


# --------------------------------------------------------------------------
# Settings (.env) — reloaded automatically when the file changes
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Settings:
    email: str
    password: str
    public: bool
    networks: tuple
    bad_entries: tuple
    fingerprint: str

    @property
    def credentials_ready(self) -> bool:
        return bool(self.email) and bool(self.password) and self.password != PLACEHOLDER_PASSWORD


def parse_env(text: str) -> dict:
    data = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        data[key] = value
    return data


def build_settings(data: dict) -> Settings:
    email = data.get("FILESPACE_EMAIL", "").strip()
    password = data.get("FILESPACE_PASSWORD", "")
    public = data.get("FILESPACE_PUBLIC", "false").strip().lower() in TRUE_VALUES
    networks, bad = [], []
    for raw in re.split(r"[,\s;]+", data.get("FILESPACE_ALLOWED_IPS", "")):
        if not raw:
            continue
        try:
            networks.append(ipaddress.ip_network(raw, strict=False))
        except ValueError:
            bad.append(raw)
    fingerprint = hashlib.sha256(f"{email.lower()}\0{password}".encode("utf-8")).hexdigest()
    return Settings(email, password, public, tuple(networks), tuple(bad), fingerprint)


def describe(s: Settings) -> str:
    if s.public:
        mode = "PUBLIC (any device can reach the login page)"
    else:
        mode = f"RESTRICTED ({len(s.networks)} allowed IP entr{'y' if len(s.networks) == 1 else 'ies'}: " \
               f"{', '.join(str(n) for n in s.networks) or 'none'})"
    extra = f" | ignored invalid IPs: {', '.join(s.bad_entries)}" if s.bad_entries else ""
    return f"{mode}{extra}"


class ConfigStore:
    def __init__(self, path: Path, on_reload=None):
        self.path = path
        self.on_reload = on_reload
        self._mtime = None
        self._lock = threading.Lock()
        self._cur: Settings | None = None
        self.refresh(force=True)

    def refresh(self, force: bool = False) -> None:
        try:
            mtime = self.path.stat().st_mtime_ns
        except OSError:
            return
        if not force and mtime == self._mtime:
            return
        with self._lock:
            if not force and mtime == self._mtime:
                return
            try:
                text = self.path.read_text(encoding="utf-8-sig")
            except OSError:
                return  # keep the previous settings (e.g. editor mid-save)
            first = self._cur is None
            self._cur = build_settings(parse_env(text))
            self._mtime = mtime
            if not first:
                print(f"[config] .env reloaded -> {describe(self._cur)}", flush=True)
                if self.on_reload:
                    self.on_reload(self._cur)

    def get(self) -> Settings:
        self.refresh()
        assert self._cur is not None
        return self._cur


# --------------------------------------------------------------------------
# Sessions and login throttling
# --------------------------------------------------------------------------
class SessionStore:
    def __init__(self, on_end=None):
        self._d: dict[str, list] = {}   # token -> [fingerprint, created, last_active, ip]
        self._lock = threading.Lock()
        self.on_end = on_end

    def _ended(self, ip: str, why: str) -> None:
        if self.on_end:
            self.on_end(ip, why)

    def create(self, fingerprint: str, ip: str = "-") -> str:
        token = secrets.token_urlsafe(32)
        now = time.time()
        expired = []
        with self._lock:
            for t, (_, created, last, sip) in list(self._d.items()):
                if now - last > SESSION_IDLE_SECONDS or now - created > SESSION_MAX_SECONDS:
                    expired.append(sip)
                    del self._d[t]
            self._d[token] = [fingerprint, now, now, ip]
        for sip in expired:
            self._ended(sip, "session expired")
        return token

    def valid(self, token: str, fingerprint: str, touch: bool = True) -> bool:
        now = time.time()
        why = None
        with self._lock:
            item = self._d.get(token)
            if not item:
                return False
            fp, created, last, ip = item
            if fp != fingerprint:
                why = "credentials changed in .env"
            elif now - last > SESSION_IDLE_SECONDS:
                why = f"inactive for {SESSION_IDLE_SECONDS // 60} minutes"
            elif now - created > SESSION_MAX_SECONDS:
                why = "maximum session length reached"
            if why:
                del self._d[token]
            elif touch:
                item[2] = now
        if why:
            self._ended(ip, "session ended: " + why)
            return False
        return True

    def remaining(self, token) -> int:
        with self._lock:
            item = self._d.get(token or "")
            if not item:
                return 0
            now = time.time()
            left = min(item[2] + SESSION_IDLE_SECONDS, item[1] + SESSION_MAX_SECONDS) - now
            return int(max(0, left))

    def destroy(self, token: str) -> None:
        with self._lock:
            self._d.pop(token, None)

    def count(self) -> int:
        with self._lock:
            return len(self._d)


class Throttle:
    def __init__(self):
        self._d: dict[str, list] = {}   # ip -> [failures, locked_until, last_failure]
        self._lock = threading.Lock()

    def locked_for(self, ip: str) -> int:
        with self._lock:
            item = self._d.get(ip)
            if not item:
                return 0
            remaining = int(item[1] - time.time())
            return remaining if remaining > 0 else 0

    def fail(self, ip: str) -> int:
        now = time.time()
        with self._lock:
            item = self._d.setdefault(ip, [0, 0.0, now])
            if now - item[2] > LOGIN_LOCK_SECONDS:
                item[0] = 0
            item[0] += 1
            item[2] = now
            if item[0] >= MAX_LOGIN_FAILURES:
                item[1] = now + LOGIN_LOCK_SECONDS
                item[0] = 0
                return LOGIN_LOCK_SECONDS
            return 0

    def ok(self, ip: str) -> None:
        with self._lock:
            self._d.pop(ip, None)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def fmt_path(value: str) -> str:
    """Normalise a relative path. (parse_qs already URL-decodes the value.)"""
    return (value or "").replace("\\", "/").strip("/")


def skip_name(name: str) -> bool:
    return name in SKIP_DIRS or name.startswith(".")


def hidden_attr(st: os.stat_result) -> bool:
    attrs = getattr(st, "st_file_attributes", 0)
    return bool(attrs & 0x2 or attrs & 0x4)   # HIDDEN or SYSTEM


def local_ips() -> list[str]:
    found = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in found:
                found.append(ip)
    except OSError:
        pass
    return found


def ensure_env_file(path: Path) -> None:
    if path.exists():
        return
    path.write_text(ENV_TEMPLATE, encoding="utf-8")
    raise SystemExit(
        f"\nCreated a settings file at: {path}\n"
        "Open it, set FILESPACE_EMAIL, FILESPACE_PASSWORD and FILESPACE_ALLOWED_IPS,\n"
        "then run this script again.\n")


def create_desktop_shortcut(script_path: Path, env_path: Path) -> None:
    """Create or update the FileSpace launcher shortcut for this user."""
    powershell = r"""
$ErrorActionPreference = 'Stop'
$desktop = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktop 'File Server.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $env:FILESPACE_SHORTCUT_TARGET
$shortcut.Arguments = $env:FILESPACE_SHORTCUT_ARGUMENTS
$shortcut.WorkingDirectory = $env:FILESPACE_SHORTCUT_WORKING_DIRECTORY
$shortcut.Description = 'Start the FileSpace server'
$shortcut.Save()
Write-Output $shortcutPath
"""
    try:
        environment = os.environ.copy()
        cmd = Path(os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"))
        python = str(sys.executable)
        arguments = f'/k ""{python}" "{script_path}" --env "{env_path}""'
        environment.update({
            "FILESPACE_SHORTCUT_TARGET": str(cmd),
            "FILESPACE_SHORTCUT_ARGUMENTS": arguments,
            "FILESPACE_SHORTCUT_WORKING_DIRECTORY": str(script_path.parent),
        })
        result = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-NonInteractive",
                "-ExecutionPolicy", "Bypass", "-Command", powershell,
            ],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
        shortcut = Path(result.stdout.strip().splitlines()[-1])
        print(f" Shortcut    : {shortcut}")
    except (OSError, subprocess.CalledProcessError) as e:
        detail = e.stderr.strip() if isinstance(e, subprocess.CalledProcessError) and e.stderr else str(e)
        print(f" WARNING     : could not create desktop shortcut ({detail})", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Start the FileSpace browser.")
    parser.add_argument(
        "--root", default=None,
        help="Root folder to share (default: FILESPACE_ROOT from .env, or D:\\)",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (0.0.0.0 allows other devices; default)")
    parser.add_argument("--port", type=int, default=6789, help="Port (default: 6789)")
    parser.add_argument("--env", default=str(Path(__file__).resolve().with_name(".env")),
                        help="Path to the settings file (default: .env next to this script)")
    parser.add_argument("--log", default=str(Path(__file__).resolve().with_name("logs.txt")),
                        help="Activity log file (default: logs.txt next to this script)")
    args = parser.parse_args()

    env_path = Path(args.env).resolve()
    ensure_env_file(env_path)
    try:
        env_data = parse_env(env_path.read_text(encoding="utf-8-sig"))
    except OSError as e:
        raise SystemExit(f"Cannot read settings file {env_path}: {e}")

    root_value = args.root if args.root is not None else env_data.get("FILESPACE_ROOT", "D:\\")
    root = Path(root_value).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"Root directory does not exist: {root}")
    if env_data.get("FILESPACE_CREATE_SHORTCUT", "").strip().lower() in TRUE_VALUES:
        create_desktop_shortcut(Path(__file__).resolve(), env_path)

    log = ActivityLog(Path(args.log).resolve())
    store = ConfigStore(env_path, on_reload=lambda c: log.write("-", "CONFIG_RELOAD", describe(c)))
    sessions = SessionStore(on_end=lambda ip, why: log.write(ip, "SESSION_END", why))
    throttle = Throttle()

    # --- never share the FileSpace app itself (script, .env, logs) -----------
    app_file = Path(__file__).resolve()
    app_dir = app_file.parent
    excluded_files = {app_file, env_path, log.path, log.path.with_name(log.path.stem + ".old" + log.path.suffix)}
    excluded = set(excluded_files)
    if app_dir != root and app_dir not in root.parents:   # unless the user deliberately shares inside it
        excluded.add(app_dir)
    excluded_norm = {os.path.normcase(str(p)) for p in excluded}

    def is_excluded(path_str) -> bool:
        n = os.path.normcase(os.path.abspath(str(path_str)))
        return any(n == ex or n.startswith(ex + os.sep) for ex in excluded_norm)

    thumbs = ThumbCache()
    ffmpeg = shutil.which("ffmpeg")
    playback_cache = Path(tempfile.gettempdir()) / "filespace-playback-cache"
    playback_cache.mkdir(parents=True, exist_ok=True)
    playback_locks: dict[str, threading.Lock] = {}
    playback_locks_guard = threading.Lock()

    def get_playable_video(source: Path) -> Path:
        """Create and reuse a browser-compatible MP4 for an MKV source."""
        try:
            stat = source.stat()
        except OSError:
            raise FileNotFoundError
        key = hashlib.sha256(
            f"{os.path.normcase(str(source))}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8")
        ).hexdigest()
        output = playback_cache / f"{key}.mp4"
        if output.is_file() and output.stat().st_size > 0:
            return output
        if not ffmpeg:
            raise RuntimeError(
                "Browser playback requires FFmpeg. Install FFmpeg and restart FileSpace."
            )
        with playback_locks_guard:
            lock = playback_locks.setdefault(key, threading.Lock())
        with lock:
            if output.is_file() and output.stat().st_size > 0:
                return output
            temporary = output.with_suffix(".tmp.mp4")
            try:
                if temporary.exists():
                    temporary.unlink()
                log.write("-", "TRANSCODE_START", f"{source.name} -> browser MP4")
                result = subprocess.run(
                    [ffmpeg, "-y", "-i", str(source), "-map", "0:v:0", "-map", "0:a:0?",
                     "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                     "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
                     str(temporary)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                    check=False,
                )
                if result.returncode != 0 or not temporary.is_file() or temporary.stat().st_size == 0:
                    detail = (result.stderr or "FFmpeg did not produce an output file").strip()
                    raise RuntimeError(f"FFmpeg could not prepare this video: {detail[-500:]}")
                os.replace(temporary, output)
                log.write("-", "TRANSCODE_DONE", f"{source.name} ({output.stat().st_size} bytes)")
                return output
            finally:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass
                except OSError:
                    pass

    def run_health_checks(cfg: Settings) -> list:
        out = []

        def add(name, status, detail):
            out.append({"name": name, "status": status, "detail": detail})

        try:
            with os.scandir(root) as it:
                next(it, None)
            add("Shared folder", "ok", "Readable")
        except OSError as e:
            add("Shared folder", "fail", f"Cannot read it ({e.strerror or e})")
        try:
            free = shutil.disk_usage(root).free
            add("Disk space", "ok" if free > (1 << 30) else "warn", f"{fmt_bytes(free)} free")
        except OSError:
            add("Disk space", "warn", "Could not be checked")
        try:
            with open(log.path, "a", encoding="utf-8"):
                pass
            add("Activity log", "ok", "Writable")
        except OSError:
            add("Activity log", "fail", "logs.txt is not writable")
        if env_path.is_file():
            add("Settings file", "ok", ".env loaded")
        else:
            add("Settings file", "fail", ".env is missing")
        if not cfg.credentials_ready:
            add("Login", "fail", "Set a real email and password in .env")
        elif len(cfg.password) < 8:
            add("Login", "warn", "Password is short (use 8+ characters)")
        else:
            add("Login", "ok", f"Configured · {sessions.count()} active session(s)")
        if cfg.public:
            add("Access", "warn", "Public: any device can reach the login page")
        else:
            n = len(cfg.networks)
            add("Access", "ok", f"Restricted to {n} allowed IP entr{'y' if n == 1 else 'ies'} + this PC")
        if ffmpeg:
            add("Browser video", "ok", "FFmpeg is available for MKV playback")
        else:
            add("Browser video", "warn", "Install FFmpeg to play MKV videos in the browser")
        add("App files", "ok", "FileSpace folder, .env and logs are hidden from sharing")
        add("Thumbnails", "ok", "Fast (Pillow)" if HAVE_PIL else "Basic (pip install pillow for faster thumbnails)")
        return out

    root_label = root.name or str(root)
    boot = "const BOOT=" + json.dumps({"root": root_label, "idle": SESSION_IDLE_SECONDS}).replace("</", "<\\/") + ";"
    page_html = PAGE.replace("/*__BOOT__*/", boot)

    def resolve(rel: str) -> Path:
        parts = [p for p in rel.split("/") if p]
        for p in parts:
            if p in (".", "..") or ":" in p or p.endswith((".", " ")) or skip_name(p):
                raise PermissionError("Access denied")
        target = root.joinpath(*parts).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            raise PermissionError("Access denied")
        if is_excluded(target):
            raise PermissionError("Access denied")
        if not target.exists():
            raise FileNotFoundError("Not found")
        return target

    def make_entry(name: str, rel: str, is_dir: bool, st: os.stat_result) -> dict:
        return {
            "name": name,
            "is_dir": is_dir,
            "relative_path": f"{rel}/{name}" if rel else name,
            "extension": "" if is_dir else os.path.splitext(name)[1].lstrip(".").upper(),
            "type": "Folder" if is_dir else (mimetypes.guess_type(name)[0] or "File"),
            "kind": "folder" if is_dir else kind_of(name),
            "modified": st.st_mtime,
            "size": None if is_dir else st.st_size,
        }

    class Handler(BaseHTTPRequestHandler):
        server_version = "FileSpace/2.0"

        def log_message(self, fmt, *a):
            print(f"[{self.log_date_time_string()}] {self.client_address[0]} - {fmt % a}")

        # ---- low-level responses -------------------------------------
        def _start(self, status, content_type, length=None, extra=None, csp=CSP, frame=False):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            if length is not None:
                self.send_header("Content-Length", str(length))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "SAMEORIGIN" if frame else "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")
            if csp:
                self.send_header("Content-Security-Policy", csp)
            for k, v in (extra or []):
                self.send_header(k, v)
            self.end_headers()

        def send_bytes(self, status, content, content_type="application/json; charset=utf-8", extra=None):
            self._start(status, content_type, len(content), extra)
            self.wfile.write(content)

        def send_json(self, status, obj, extra=None):
            self.send_bytes(status, json.dumps(obj).encode("utf-8"), extra=extra)

        def send_html(self, status, html):
            self.send_bytes(status, html.encode("utf-8"), "text/html; charset=utf-8")

        # ---- access control ------------------------------------------
        def client_ip(self) -> str:
            return self.client_address[0]

        def ip_allowed(self, cfg: Settings) -> bool:
            if cfg.public:
                return True
            try:
                ip = ipaddress.ip_address(self.client_ip())
            except ValueError:
                return False
            if ip.version == 6 and ip.ipv4_mapped:
                ip = ip.ipv4_mapped
            if ip.is_loopback:
                return True
            return any(ip in net for net in cfg.networks if net.version == ip.version)

        def session_token(self):
            raw = self.headers.get("Cookie")
            if not raw:
                return None
            try:
                jar = SimpleCookie()
                jar.load(raw)
            except Exception:
                return None
            morsel = jar.get(COOKIE_NAME)
            return morsel.value if morsel else None

        def authed(self, cfg: Settings, touch: bool = True) -> bool:
            token = self.session_token()
            return bool(token) and sessions.valid(token, cfg.fingerprint, touch)

        def deny(self):
            print(f"[blocked] {self.client_ip()} is not in FILESPACE_ALLOWED_IPS", flush=True)
            log.write(self.client_ip(), "BLOCKED_IP", f"{self.command} {self.path}")
            self.send_bytes(403, b"Access denied for this device.\n", "text/plain; charset=utf-8")

        # ---- routes ---------------------------------------------------
        def do_GET(self):
            cfg = store.get()
            if not self.ip_allowed(cfg):
                return self.deny()
            parsed = urlparse(self.path)
            route = parsed.path
            try:
                if route == "/healthz":
                    return self.api_healthz()
                if route == "/":
                    return self.send_html(200, page_html if self.authed(cfg) else LOGIN_PAGE)
                if route.startswith("/api/"):
                    if not self.authed(cfg, touch=(route != "/api/health")):
                        if route != "/api/health":
                            log.write(self.client_ip(), "UNAUTHORIZED", f"{route} without a valid session")
                        return self.send_json(401, {"error": "Please sign in."})
                    query = parse_qs(parsed.query)
                    rel = fmt_path(query.get("path", [""])[0])
                    if route == "/api/list":
                        return self.api_list(rel)
                    if route == "/api/search":
                        return self.api_search(rel, query.get("q", [""])[0].strip())
                    if route == "/api/download":
                        return self.api_download(rel)
                    if route == "/api/file":
                        return self.api_download(rel, inline=True)
                    if route == "/api/playback":
                        return self.api_playback(rel)
                    if route == "/api/thumb":
                        return self.api_thumb(rel)
                    if route == "/api/health":
                        return self.api_health(cfg)
                    if route == "/api/keepalive":
                        return self.send_json(200, {"ok": True, "idle_left": sessions.remaining(self.session_token()),
                                                    "idle_limit": SESSION_IDLE_SECONDS})
                self.send_json(404, {"error": "Not found"})
            except PermissionError as e:
                log.write(self.client_ip(), "ACCESS_DENIED", f"{route} path={parse_qs(parsed.query).get('path', [''])[0]}")
                self.send_json(403, {"error": str(e) or "Access denied"})
            except FileNotFoundError:
                self.send_json(404, {"error": "Not found"})
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            except RuntimeError as e:
                print(f"[error] {self.path}: {e}", flush=True)
                try:
                    self.send_json(503, {"error": str(e)})
                except OSError:
                    pass
            except Exception as e:  # keep the server alive
                print(f"[error] {self.path}: {e!r}", flush=True)
                try:
                    self.send_json(500, {"error": "Server error"})
                except OSError:
                    pass

        def do_POST(self):
            cfg = store.get()
            if not self.ip_allowed(cfg):
                return self.deny()
            route = urlparse(self.path).path
            try:
                if route == "/login":
                    return self.api_login(cfg)
                if route == "/logout":
                    token = self.session_token()
                    if token:
                        sessions.destroy(token)
                    reason = parse_qs(urlparse(self.path).query).get("reason", [""])[0]
                    log.write(self.client_ip(), "LOGOUT", "signed out after inactivity" if reason == "idle" else "")
                    expire = f"{COOKIE_NAME}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"
                    return self.send_json(200, {"ok": True}, extra=[("Set-Cookie", expire)])
                self.send_json(404, {"error": "Not found"})
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        # ---- login ----------------------------------------------------
        def api_login(self, cfg: Settings):
            ip = self.client_ip()
            wait = throttle.locked_for(ip)
            if wait:
                log.write(ip, "LOGIN_LOCKED", f"attempt while locked out ({wait}s left)")
                return self.send_json(429, {"error": f"Too many attempts. Try again in {max(1, wait // 60)} minute(s)."},
                                      extra=[("Retry-After", str(wait))])
            if not cfg.credentials_ready:
                log.write(ip, "LOGIN_OFF", "credentials not configured in .env")
                return self.send_json(503, {"error": "Server login is not configured yet. Edit the .env file."})
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if length <= 0 or length > 4096:
                    raise ValueError
                body = json.loads(self.rfile.read(length))
                email, password = str(body.get("email", "")), str(body.get("password", ""))
            except (ValueError, AttributeError, UnicodeDecodeError):
                return self.send_json(400, {"error": "Bad request."})
            ok_email = hmac.compare_digest(email.strip().lower().encode("utf-8"), cfg.email.lower().encode("utf-8"))
            ok_pass = hmac.compare_digest(password.encode("utf-8"), cfg.password.encode("utf-8"))
            if ok_email and ok_pass:
                throttle.ok(ip)
                token = sessions.create(cfg.fingerprint, ip)
                cookie = f"{COOKIE_NAME}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_MAX_SECONDS}"
                print(f"[login] success from {ip}", flush=True)
                log.write(ip, "LOGIN_OK", f"email={email.strip()}")
                return self.send_json(200, {"ok": True}, extra=[("Set-Cookie", cookie)])
            time.sleep(0.6)
            locked = throttle.fail(ip)
            print(f"[login] FAILED from {ip}" + (" (now locked out)" if locked else ""), flush=True)
            log.write(ip, "LOGIN_FAIL", f"email={email.strip()}" + (" -> IP locked out 15 min" if locked else ""))
            if locked:
                return self.send_json(429, {"error": f"Too many attempts. Try again in {locked // 60} minutes."},
                                      extra=[("Retry-After", str(locked))])
            self.send_json(401, {"error": "Incorrect email or password."})

        # ---- file API -------------------------------------------------
        def api_list(self, rel: str):
            target = resolve(rel)
            if not target.is_dir():
                raise FileNotFoundError
            entries = []
            try:
                with os.scandir(target) as it:
                    for de in it:
                        if skip_name(de.name) or is_excluded(de.path):
                            continue
                        try:
                            st = de.stat()
                            is_dir = de.is_dir()
                        except OSError:
                            continue
                        if hidden_attr(st):
                            continue
                        entries.append(make_entry(de.name, rel, is_dir, st))
            except PermissionError:
                return self.send_json(403, {"error": "Windows denied access to this folder."})
            log.write(self.client_ip(), "LIST", f"/{rel} ({len(entries)} items)")
            self.send_json(200, {"path": rel, "entries": entries, "thumbs": HAVE_PIL})

        def api_search(self, rel: str, q: str):
            if len(q) < 2:
                return self.send_json(200, {"path": rel, "entries": [], "truncated": False})
            base = resolve(rel)
            if not base.is_dir():
                raise FileNotFoundError
            needle = q.lower()
            results, scanned, truncated = [], 0, False
            queue = deque([(base, rel)])
            while queue:
                folder, folder_rel = queue.popleft()
                try:
                    it = os.scandir(folder)
                except OSError:
                    continue
                with it:
                    for de in it:
                        if skip_name(de.name) or is_excluded(de.path):
                            continue
                        scanned += 1
                        if scanned > SEARCH_MAX_SCANNED or len(results) >= SEARCH_MAX_RESULTS:
                            truncated = True
                            queue.clear()
                            break
                        try:
                            st = de.stat()
                            is_dir = de.is_dir(follow_symlinks=False)
                        except OSError:
                            continue
                        if hidden_attr(st):
                            continue
                        if needle in de.name.lower():
                            results.append(make_entry(de.name, folder_rel, is_dir, st))
                        if is_dir:
                            queue.append((Path(de.path), f"{folder_rel}/{de.name}" if folder_rel else de.name))
            log.write(self.client_ip(), "SEARCH", f"q={q!r} in /{rel} ({len(results)} results)")
            self.send_json(200, {"path": rel, "entries": results, "truncated": truncated, "thumbs": HAVE_PIL})

        def api_thumb(self, rel: str):
            target = resolve(rel)
            if not target.is_file() or file_ext(target.name) not in THUMB_EXTS:
                raise FileNotFoundError
            st = target.stat()
            if hidden_attr(st):
                raise PermissionError("Access denied")
            data = thumbs.get(target, st)
            if not data:
                return self.send_json(404, {"error": "No thumbnail"})
            self.send_bytes(200, data, "image/jpeg")

        def api_health(self, cfg: Settings):
            checks = run_health_checks(cfg)
            order = {"ok": 0, "warn": 1, "fail": 2}
            overall = max((c["status"] for c in checks), key=lambda x: order[x], default="ok")
            self.send_json(200, {"status": overall, "uptime": int(time.time() - START_TIME),
                                 "idle_left": sessions.remaining(self.session_token()),
                                 "idle_limit": SESSION_IDLE_SECONDS, "checks": checks})

        def api_healthz(self):
            """Public, minimal liveness probe (still limited by the IP allowlist)."""
            try:
                with os.scandir(root) as it:
                    next(it, None)
                self.send_json(200, {"status": "ok"})
            except OSError:
                self.send_json(503, {"status": "fail"})

        def api_download(self, rel: str, inline: bool = False):
            target = resolve(rel)
            if not target.is_file():
                raise FileNotFoundError
            return self.serve_file(target, rel, inline)

        def api_playback(self, rel: str):
            target = resolve(rel)
            if not target.is_file():
                raise FileNotFoundError
            if kind_of(target.name) != "video" or file_ext(target.name) != "mkv":
                return self.api_download(rel, inline=True)
            playable = get_playable_video(target)
            return self.serve_file(playable, rel + " [browser playback]", True,
                                   content_type="video/mp4")

        def serve_file(self, target: Path, rel: str, inline: bool = False, content_type: str | None = None):
            st = target.stat()
            if hidden_attr(st):
                raise PermissionError("Access denied")
            ctype, csp, disp = "application/octet-stream", CSP, "attachment"
            if inline:
                kind = kind_of(target.name)
                if kind not in ("image", "video", "audio", "pdf", "text"):
                    return self.send_json(415, {"error": "Preview is not available for this file type."})
                ctype = content_type or PREVIEW[file_ext(target.name)][1]
                disp = "inline"
                # only SVG can carry script, so it is served sandboxed; PDFs need no CSP for the browser viewer
                csp = INLINE_SVG_CSP if file_ext(target.name) == "svg" else None
            size = st.st_size
            start, end, status = 0, size - 1, 200
            rng = self.headers.get("Range", "")
            if size > 0 and rng.startswith("bytes=") and "," not in rng:
                a, _, b = rng[6:].partition("-")
                try:
                    if a == "":
                        start = max(size - int(b), 0)
                    else:
                        start = int(a)
                        end = int(b) if b else size - 1
                except ValueError:
                    start, end = 0, size - 1
                else:
                    if start > end or start >= size:
                        return self._start(416, "text/plain", 0, [("Content-Range", f"bytes */{size}")])
                    end = min(end, size - 1)
                    status = 206
            length = max(end - start + 1, 0)
            display_name = Path(rel).name
            ascii_name = re.sub(r'[^\x20-\x7e]|["\\;]', "_", display_name)
            extra = [
                ("Content-Disposition", f"{disp}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(display_name)}"),
                ("Accept-Ranges", "bytes"),
            ]
            if status == 206:
                extra.append(("Content-Range", f"bytes {start}-{end}/{size}"))
            self._start(status, ctype, length, extra, csp=csp, frame=inline)
            if not inline:
                log.write(self.client_ip(), "DOWNLOAD",
                          f"/{rel} ({length} of {size} bytes" + (f", range {start}-{end}" if status == 206 else "") + ")")
            elif status == 200 or start == 0:   # log a preview once, not every video seek
                log.write(self.client_ip(), "VIEW", f"/{rel} ({size} bytes)")
            try:
                with open(target, "rb") as fh:
                    fh.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = fh.read(min(CHUNK, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError):
                pass

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    httpd.daemon_threads = True

    cfg = store.get()
    log.write("-", "SERVER_START", f"port {args.port}, root {root}, {describe(cfg)}")
    line = "=" * 56
    print(line)
    print(" FileSpace is running")
    print(f" Shared root : {root}")
    print(f" Settings    : {env_path}")
    print(f" Activity log: {log.path}")
    print(f" Not shared  : {', '.join(sorted(str(p) for p in excluded if p == app_dir)) or 'app files'} (FileSpace folder, .env, logs)")
    print(f" Auto logout : after {SESSION_IDLE_SECONDS // 60} minutes of inactivity")
    print(f" Local URL   : http://127.0.0.1:{args.port}/")
    if args.host in ("0.0.0.0", ""):
        for ip in local_ips():
            print(f" Network URL : http://{ip}:{args.port}/")
    print(" Read-only   : file changes/deletes/uploads are disabled")
    print(f" Access      : {describe(cfg)}")
    if not cfg.credentials_ready:
        print(" WARNING     : set a real FILESPACE_EMAIL / FILESPACE_PASSWORD in .env; logins are disabled until then")
    if cfg.public:
        print(" WARNING     : PUBLIC mode - anyone who finds this address can attempt to log in")
    print(" Health check:")
    for c in run_health_checks(cfg):
        tag = {"ok": "OK  ", "warn": "WARN", "fail": "FAIL"}[c["status"]]
        print(f"   [{tag}] {c['name']}: {c['detail']}")
        if c["status"] != "ok":
            log.write("-", "HEALTH", f"{c['status'].upper()} {c['name']}: {c['detail']}")
    print(" Stop server : press Ctrl+C")
    print(" SECURITY    : plain HTTP is not encrypted; use a VPN or trusted networks")
    print(line, flush=True)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping FileSpace...")
    finally:
        log.write("-", "SERVER_STOP", "")
        httpd.server_close()


if __name__ == "__main__":
    main()