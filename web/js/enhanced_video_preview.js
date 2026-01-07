import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

// --- ЛОГИКА КОНТЕКСТНОГО МЕНЮ ПРОВОДНИКА ---
async function showFolderContextMenu(path, event, targetWidget, app) {
    let data;
    try {
        const response = await api.fetchApi("/enhanced_preview/list_dirs", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ path: path })
        });
        
        if (!response.ok) throw new Error("Network response was not ok");
        data = await response.json();
        
        if (data.error) {
            alert("Error: " + data.error);
            return;
        }
    } catch (e) {
        alert("Cannot list folders: " + e);
        return;
    }

    const menuValues = [];
    const menuOptions = [];

    if (data.parent_path && data.parent_path !== data.current_path) {
        menuValues.push("⬅️ UP");
        menuOptions.push({ 
            content: "⬅️ UP", 
            callback: () => { showFolderContextMenu(data.parent_path, event, targetWidget, app); } 
        });
    }

    menuValues.push(`✅ SELECT: ${data.current_path}`);
    menuOptions.push({
        content: `✅ SELECT THIS FOLDER`,
        callback: () => {
            targetWidget.value = data.current_path;
            if(targetWidget.callback) targetWidget.callback(targetWidget.value);
            app.graph.setDirtyCanvas(true, true);
        }
    });
    
    menuValues.push(null); 
    menuOptions.push(null);

    if (data.dirs && data.dirs.length > 0) {
        data.dirs.forEach(dirName => {
            menuValues.push("📁 " + dirName);
            menuOptions.push({
                content: "📁 " + dirName,
                callback: () => {
                    const sep = data.current_path.includes("/") ? "/" : "\\";
                    let newPath = data.current_path;
                    if (!newPath.endsWith(sep)) { newPath += sep; }
                    newPath += dirName;
                    showFolderContextMenu(newPath, event, targetWidget, app);
                }
            });
        });
    } else {
        menuValues.push("(Empty folder)");
        menuOptions.push({ content: "(Empty folder)", disabled: true });
    }

    new LiteGraph.ContextMenu(menuValues, {
        event: event, 
        parentMenu: null,
        callback: function(value, options, event) {
            const idx = menuValues.indexOf(value);
            if(menuOptions[idx] && menuOptions[idx].callback) {
                menuOptions[idx].callback();
            }
        }
    });
}

// --- РЕГИСТРАЦИЯ НОДЫ ---
app.registerExtension({
    name: "Comfy.EnhancedVideoPreview",
    
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "EnhancedVideoPreview") {
            
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function() {
                if(onNodeCreated) onNodeCreated.apply(this, arguments);
                
                const saveToggle = this.widgets.find(w => w.name === "save_video_on_disk");
                const pathWidget = this.widgets.find(w => w.name === "save_path");
                const prefixWidget = this.widgets.find(w => w.name === "filename_prefix");
                
                let browseBtn = null;

                // Добавляем кнопку
                if (pathWidget) {
                     browseBtn = this.addWidget("button", "📂 Choose Dir For Saving", null, (widget, canvas, node, pos, event) => {
                        // Если отключено сохранение - кнопка не работает
                        if (widget.disabled) return;
                        const startPath = pathWidget.value;
                        showFolderContextMenu(startPath, event, pathWidget, app);
                    });
                }

                // Функция обновления состояния виджетов (блокировка)
                const updateWidgets = () => {
                    const enabled = saveToggle.value;
                    if (pathWidget) pathWidget.disabled = !enabled;
                    if (prefixWidget) prefixWidget.disabled = !enabled;
                    if (browseBtn) browseBtn.disabled = !enabled;
                    
                    // Визуально перерисовываем
                    app.graph.setDirtyCanvas(true, true);
                };

                // Вешаем callback на переключатель
                if (saveToggle) {
                    saveToggle.callback = updateWidgets;
                    // Инициализируем при старте
                    setTimeout(updateWidgets, 100);
                }
            };

            const getExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
            nodeType.prototype.getExtraMenuOptions = function(_, options) {
                if (getExtraMenuOptions) {
                    getExtraMenuOptions.apply(this, arguments);
                }

                const widget = this.widgets?.find((w) => w.name === "video_preview");
                if (!widget) return;

                const isHidden = widget.element.style.display === "none";
                const url = widget.videoElement?.src;
                const filename = url ? url.split('/').pop().split('?')[0] : "video.mp4";

                const myMenuOptions = [];

                myMenuOptions.push({
                    content: isHidden ? "👁️ Show Preview" : "🙈 Hide Preview",
                    callback: () => {
                        if (isHidden) {
                            widget.element.style.display = "flex";
                        } else {
                            widget.element.style.display = "none";
                            this.lastVideoSize = [...this.size];
                            this.setSize([this.size[0], 60]); 
                        }
                        this.setDirtyCanvas(true, true);
                    }
                });

                if (url && !isHidden) {
                    myMenuOptions.push(
                        { content: "🎬 Open Video in New Tab", callback: () => { window.open(url, "_blank"); }},
                        { content: "💾 Save Video As...", callback: () => {
                            const a = document.createElement("a");
                            a.href = url;
                            a.download = filename;
                            document.body.appendChild(a);
                            a.click();
                            document.body.removeChild(a);
                        }}
                    );
                }
                if (myMenuOptions.length > 0) {
                    myMenuOptions.push(null);
                }
                options.splice(0, 0, ...myMenuOptions);
            };

            const onExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (message) {
                if (onExecuted) {
                    onExecuted.apply(this, arguments);
                }

                let items = [];
                if (message.videos) items = items.concat(message.videos);
                if (message.gifs) items = items.concat(message.gifs);

                if (items.length === 0) return;

                const previewData = items[0];
                const filename = previewData.filename;
                const subfolder = previewData.subfolder;
                const type = previewData.type || "output";
                
                const opts = previewData.options || {};
                const shouldAutoplay = opts.autoplay !== undefined ? opts.autoplay : true;
                const shouldMute = opts.mute !== undefined ? opts.mute : false;
                const shouldLoop = opts.loop !== undefined ? opts.loop : true;

                const params = new URLSearchParams({ filename: filename, subfolder: subfolder, type: type });
                const url = api.apiURL("/view?" + params.toString());

                let widget = this.widgets?.find((w) => w.name === "video_preview");
                
                if (!widget) {
                    const div = document.createElement("div");
                    div.style.width = "100%";
                    div.style.height = "100%";
                    div.style.display = "flex";
                    div.style.justifyContent = "center";
                    div.style.alignItems = "center";
                    
                    const video = document.createElement("video");
                    video.controls = true;
                    video.style.width = "100%";
                    video.style.height = "100%";
                    video.style.objectFit = "contain"; 
                    
                    video.addEventListener("contextmenu", (e) => {
                        e.preventDefault(); 
                        e.stopPropagation();
                        app.canvas.selectNode(this);
                        app.canvas.processContextMenu(this, e);
                    });

                    div.appendChild(video);

                    widget = this.addDOMWidget("video_preview", "video", div, { serialize: false, hideOnZoom: false });
                    widget.videoElement = video;
                    
                    video.onloadedmetadata = () => {
                       if (widget.element.style.display === "none") return;
                       const videoWidth = video.videoWidth;
                       const videoHeight = video.videoHeight;
                       const ratio = videoWidth / videoHeight;
                       const targetWidth = Math.min(600, videoWidth);
                       const targetHeight = targetWidth / ratio;
                       this.setSize([targetWidth, targetHeight + 100]);
                       app.graph.setDirtyCanvas(true, true);
                    };
                }

                const videoEl = widget.videoElement;
                videoEl.loop = shouldLoop;
                videoEl.muted = shouldMute;
                videoEl.autoplay = shouldAutoplay;

                const timeStampedUrl = url + "&t=" + Date.now();
                if (!videoEl.src.includes(url)) {
                    videoEl.src = timeStampedUrl;
                    if (shouldAutoplay && widget.element.style.display !== "none") {
                        videoEl.play().catch(e => console.log("Autoplay blocked by browser:", e));
                    }
                }
            };
            
            const onResize = nodeType.prototype.onResize;
            nodeType.prototype.onResize = function(size) {
                if (onResize) onResize.apply(this, arguments);
            };
        }
    }
});