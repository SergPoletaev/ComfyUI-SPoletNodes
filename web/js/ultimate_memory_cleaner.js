import { app } from "../../scripts/app.js";

app.registerExtension({
    name: "UltimateMemoryCleaner.HelpButton",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "UltimateMemoryCleaner") {
            
            const description = nodeData.description || "Описание отсутствует.";

            // 1. Отрисовка кнопки "?"
            const onDrawForeground = nodeType.prototype.onDrawForeground;
            
            nodeType.prototype.onDrawForeground = function(ctx) {
                if (onDrawForeground) {
                    onDrawForeground.apply(this, arguments);
                }

                if (this.flags.collapsed) return;

                const x = this.size[0] - 20;
                const y = -15;
                const radius = 8;

                ctx.save();
                ctx.fillStyle = "#ff9900"; 
                ctx.beginPath();
                ctx.arc(x, y, radius, 0, Math.PI * 2);
                ctx.fill();

                ctx.fillStyle = "white";
                ctx.font = "bold 12px Arial";
                ctx.textAlign = "center";
                ctx.textBaseline = "middle";
                ctx.fillText("?", x, y);
                ctx.restore();
            };

            // 2. Обработка клика
            const onMouseDown = nodeType.prototype.onMouseDown;

            nodeType.prototype.onMouseDown = function(e, pos) {
                const x = this.size[0] - 20;
                const y = -15;
                const radius = 8;
                
                const dist = Math.sqrt(Math.pow(pos[0] - x, 2) + Math.pow(pos[1] - y, 2));

                if (dist <= radius) {
                    app.ui.dialog.show(description);
                    return true;
                }

                if (onMouseDown) {
                    return onMouseDown.apply(this, arguments);
                }
            };
        }
    }
});