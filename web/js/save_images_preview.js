import { app } from "/scripts/app.js";
import { api } from "/scripts/api.js";

app.registerExtension({
    name: "Comfyui.SaveImagesPreview",
    
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "Save Images & Preview") {
            
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function() {
                onNodeCreated?.apply(this, arguments);
                
                const pathWidget = this.widgets.find(w => w.name === "output_path");
                
                if (pathWidget) {
                    // Добавляем кнопку "Browse" рядом с полем
                    // При клике она откроет контекстное меню
                    this.addWidget("button", "📂 Browse", null, (widget, canvas, node, pos, event) => {
                        // Используем текущее значение из поля ввода как старт
                        const startPath = pathWidget.value;
                        showFolderContextMenu(startPath, event, pathWidget, app);
                    });
                }
            };
        }
    }
});

/**
 * Функция для вызова меню
 */
async function showFolderContextMenu(path, event, targetWidget, app) {
    
    // Получаем данные от API
    let data;
    try {
        const response = await api.fetchApi("/save_preview/list_dirs", {
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

    // Формируем пункты меню
    const menuValues = [];
    const menuOptions = [];

    // 1. Опция "Вверх"
    if (data.parent_path && data.parent_path !== data.current_path) {
        menuValues.push("⬅️ UP");
        menuOptions.push({ 
            content: "⬅️ UP", 
            callback: () => {
                // Рекурсивный вызов меню для родительской папки
                showFolderContextMenu(data.parent_path, event, targetWidget, app);
            } 
        });
    }

    // 2. Опция "Выбрать текущую"
    menuValues.push(`✅ SELECT: ${data.current_path}`);
    menuOptions.push({
        content: `✅ SELECT THIS FOLDER`,
        callback: () => {
            targetWidget.value = data.current_path;
            if(targetWidget.callback) targetWidget.callback(targetWidget.value);
            app.graph.setDirtyCanvas(true, true);
        }
    });
    
    // Разделитель
    menuValues.push(null); 
    menuOptions.push(null);

    // 3. Список папок
    if (data.dirs && data.dirs.length > 0) {
        data.dirs.forEach(dirName => {
            menuValues.push("📁 " + dirName);
            menuOptions.push({
                content: "📁 " + dirName,
                callback: () => {
                    // Определяем разделитель пути для JS
                    const sep = data.current_path.includes("/") ? "/" : "\\";
                    // Корректное соединение путей (фикс для endsWith regex ошибки)
                    let newPath = data.current_path;
                    if (!newPath.endsWith(sep)) {
                        newPath += sep;
                    }
                    newPath += dirName;
                    
                    // Рекурсивно открываем меню для новой папки
                    showFolderContextMenu(newPath, event, targetWidget, app);
                }
            });
        });
    } else {
        menuValues.push("(Empty folder)");
        menuOptions.push({ content: "(Empty folder)", disabled: true });
    }

    // Создаем ContextMenu LiteGraph
    // Важно: передаем event, чтобы меню открылось под мышкой
    new LiteGraph.ContextMenu(menuValues, {
        event: event, 
        parentMenu: null, // Нет родителя, это топ-меню
        callback: function(value, options, event) {
            // Этот callback срабатывает, если мы передаем простые строки,
            // но мы используем объекты с собственными callback внутри menuOptions,
            // поэтому здесь логика минимальна.
            const idx = menuValues.indexOf(value);
            if(menuOptions[idx] && menuOptions[idx].callback) {
                menuOptions[idx].callback();
            }
        }
    });
}