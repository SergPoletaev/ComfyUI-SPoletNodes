// Абсолютный путь, чтобы ComfyUI не ругался
import { app } from "/scripts/app.js";

app.registerExtension({
    name: "Video.BatchCrossfade",
    async nodeCreated(node) {
        // Проверяем имя класса, которое мы вернули (VideoBatchCrossfade)
        if (node.comfyClass === "VideoBatchCrossfade") {
            
            const updateInputs = () => {
                const initialWidth = node.size[0];
                const countWidget = node.widgets.find(w => w.name === "Batches_count");
                if (!countWidget) return;

                const targetCount = countWidget.value;
                
                if (!node.inputs) {
                    node.inputs = [];
                }
                
                // Фильтруем наши динамические входы
                const existingBatchInputs = node.inputs.filter(input => input.name.startsWith('Batch_'));
                const currentCount = existingBatchInputs.length;

                const getBatchName = (i) => "Batch_" + String(i).padStart(4, '0');

                // Добавление слотов
                if (currentCount < targetCount) {
                    for (let i = currentCount + 1; i <= targetCount; i++) {
                        const inputName = getBatchName(i);
                        if (!node.inputs.find(input => input.name === inputName)) {
                            node.addInput(inputName, "IMAGE");
                        }
                    }
                } 
                // Удаление слотов
                else if (currentCount > targetCount) {
                    for (let i = currentCount; i > targetCount; i--) {
                        const inputName = getBatchName(i);
                        const inputIndex = node.inputs.findIndex(input => input.name === inputName);
                        if (inputIndex > -1) {
                            node.removeInput(inputIndex);
                        }
                    }
                }
                
                node.onResize?.(node.size);
                node.size[0] = initialWidth;
            };

            const countWidget = node.widgets.find(w => w.name === "Batches_count");
            if (countWidget) {
                countWidget.callback = () => {
                    updateInputs();
                    app.graph.setDirtyCanvas(true, true);
                };
            }

            setTimeout(updateInputs, 0);
        }
    }
});