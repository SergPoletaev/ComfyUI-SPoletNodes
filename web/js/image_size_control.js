import { app } from "/scripts/app.js";

app.registerExtension({
    name: "ComfyUI.ImageSize.FinalV4",
    
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "GetImageSizeWithPreview") {
            
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
                const node = this;

                setTimeout(() => {
                    // --- 1. Инфо-поле ---
                    let infoW = node.widgets.find(w => w.name === "InfoPanel");
                    if (!infoW) {
                        infoW = node.addWidget("text", "InfoPanel", "Init...", () => {}, { multiline: true });
                    }
                    if (infoW && infoW.inputEl) {
                        infoW.inputEl.readOnly = true;
                        infoW.inputEl.style.backgroundColor = "#222";
                        infoW.inputEl.style.color = "#ccc";
                        infoW.inputEl.rows = 4;
                        infoW.inputEl.style.fontFamily = "monospace";
                        infoW.inputEl.style.textAlign = "center";
                    }

                    // --- 2. Логика ---
                    const refreshUI = () => {
                        const toggle = node.widgets.find(w => w.name === "custom_resolution");
                        const show = toggle ? toggle.value : false;

                        // 2.1. Одиночные виджеты для скрытия (Интерполяция)
                        const simpleWidgets = ["interpolation"];
                        simpleWidgets.forEach(name => {
                            const w = node.widgets.find(x => x.name === name);
                            if (!w) return;
                            if (!w.origType) w.origType = w.type;

                            if (show) {
                                if (w.type === "HIDDEN") { w.type = w.origType; w.computeSize = undefined; }
                            } else {
                                if (w.type !== "HIDDEN") { w.type = "HIDDEN"; w.computeSize = () => [0, -4]; }
                            }
                        });

                        // 2.2. Группы с шагами
                        const groups = [
                            { s: "width_step", v: "custom_width" },
                            { s: "height_step", v: "custom_height" }
                        ];

                        groups.forEach(group => {
                            const wStep = node.widgets.find(w => w.name === group.s);
                            const wVal = node.widgets.find(w => w.name === group.v);
                            
                            if (!wStep || !wVal) return;

                            if (!wStep.origType) wStep.origType = wStep.type;
                            if (!wVal.origType) wVal.origType = wVal.type;

                            if (show) {
                                // ПОКАЗАТЬ
                                if (wStep.type === "HIDDEN") { wStep.type = wStep.origType; wStep.computeSize = undefined; }
                                if (wVal.type === "HIDDEN") { wVal.type = wVal.origType; wVal.computeSize = undefined; }

                                // === УМНЫЙ СТЕППЕР ===
                                const stepAmt = wStep.value;
                                
                                if (!wVal.options) wVal.options = {};
                                wVal.options.step = stepAmt; 
                                wVal.options.min = 0;
                                
                                // Init Memory
                                if (wVal.prevValue === undefined) wVal.prevValue = wVal.value;

                                // Hook
                                if (!wVal.smartHooked) {
                                    const originalCallback = wVal.callback;
                                    wVal.callback = function(value) {
                                        const s = wStep.value;
                                        if (s > 1) {
                                            let currentSnapped = this.prevValue || 0;
                                            // Если изменение большое (ручной ввод)
                                            if (Math.abs(value - currentSnapped) > s * 1.5) {
                                                value = Math.round(value / s) * s;
                                            } else {
                                                // Маленькое (стрелка/мышь)
                                                if (value > currentSnapped) value = currentSnapped + s;
                                                else if (value < currentSnapped) value = currentSnapped - s;
                                                else value = currentSnapped;
                                            }
                                            if (value < 0) value = 0;
                                            this.value = value;
                                            this.prevValue = value;
                                        } else {
                                            this.prevValue = value;
                                        }
                                        if (originalCallback) originalCallback(value);
                                    };
                                    wVal.smartHooked = true;
                                }
                                
                                // Init Rounding
                                if (stepAmt > 1 && wVal.value > 0) {
                                    const snapped = Math.round(wVal.value / stepAmt) * stepAmt;
                                    if (wVal.value !== snapped) { wVal.value = snapped; wVal.prevValue = snapped; }
                                }

                            } else {
                                // СКРЫТЬ
                                if (wStep.type !== "HIDDEN") { wStep.type = "HIDDEN"; wStep.computeSize = () => [0, -4]; }
                                if (wVal.type !== "HIDDEN") { wVal.type = "HIDDEN"; wVal.computeSize = () => [0, -4]; }
                            }
                        });

                        // Ресайз
                        node.setSize(node.computeSize());
                        app.graph.setDirtyCanvas(true, true);
                    };

                    // --- 3. Слушатели ---
                    const toggleW = node.widgets.find(w => w.name === "custom_resolution");
                    if (toggleW) toggleW.callback = refreshUI;

                    ["width_step", "height_step"].forEach(n => {
                        const w = node.widgets.find(x => x.name === n);
                        if (w) {
                            const oldCb = w.callback;
                            w.callback = function(v) {
                                if (oldCb) oldCb(v);
                                refreshUI();
                            };
                        }
                    });

                    refreshUI();

                }, 50);

                return r;
            };

            const onExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (message) {
                onExecuted?.apply(this, arguments);
                if (message && message.text && message.text.length > 0) {
                    const w = this.widgets.find(w => w.name === "InfoPanel");
                    if (w) {
                        w.value = message.text[0];
                        if (w.inputEl) w.inputEl.value = message.text[0];
                    }
                }
            };
        }
    }
});