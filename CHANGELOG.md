# Historial de cambios

## 5.3.1 — 2026-09-24

- Ajustado el cierre de discontinuidades en la máscara de aislamiento para tolerar variaciones pequeñas de decodificación JPEG entre el entorno principal y Spyder.
- Verificada la detección en el intérprete Python 3.12 de Spyder, además del entorno principal Python 3.13.

## 5.3.0 — 2026-09-24

### Agregado

- Auto Measure: calibración manual seguida de propuestas automáticas para pares verde/amarillo, con procesamiento local mediante OpenCV.
- Puntos de control arrastrables para la regla, círculos y puente; ajuste visible durante el arrastre.
- Regla con marcas 0, mitad y longitud total, incluida en la medición manual y el informe exportado.
- Correct measurement / Edit Selected para corregir un paso aceptado, conservando los puntos posteriores como propuestas y recalculando medidas al confirmar.
- Pruebas con geometría sintética y ambas fotos suministradas, incluyendo revisión de regla y recálculo.

### Cambiado

- Todos los pasos requieren Accept Step para permitir revisar y corregir los puntos antes del cierre.
- Redraw Step permite sustituir una propuesta por puntos manuales. Ante una detección fallida se conserva la calibración y continúa el flujo manual.
- La configuración de pares, puntos y longitud de escala queda fijada al iniciar la sesión para evitar cambios silenciosos de unidades o cantidad de resultados.

La detección es una propuesta revisable, especialmente con reflejos, trazos sobre la foto o cavidades. La marca intermedia de la regla comprueba la distribución visual y no constituye una calibración independiente.

## 5.2.0 — 2026-09-24

Primera versión registrada en Git, a partir de la aplicación v5.1 suministrada y las modificaciones de esta sesión. No existía historial Git previo.

### Corregido

- Arrastre de etiquetas disponible durante la medición, con prioridad sobre la captura de puntos y conservación de su posición.
- Historial para reabrir el último cierre, incluso después de terminar la medición; invalida el resumen hasta completar nuevamente los pasos.

### Agregado

- Deslizador Image area y separador ajustable entre tabla e imagen.
- Botón Undo Last Closure y atajo Ctrl+Z. Undo Point reabre el cierre anterior cuando no quedan puntos en curso.
- Prueba de interacción con tres pares e imagen sintética.
- README en español con instalación, uso, cálculo de dimensiones y análisis de REFERENTE.jpeg.
- Dependencias verificadas, exclusiones de Git y licencia CERN-OHL-S-2.0.

El archivo principal conserva el nombre histórico para mantener el comando de ejecución existente.
