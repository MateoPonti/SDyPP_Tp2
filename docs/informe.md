# Informe TP2

## Metricas

Ejecutar `hit2/benchmark.py` con `--workers 1`, `2`, `4` y `8`, repetir cada medicion y completar la tabla:

| Workers | Tareas | Tiempo total (s) | Throughput (tareas/min) | Speedup |
|---:|---:|---:|---:|---:|
| 1 | pendiente | pendiente | pendiente | 1.00 |
| 2 | pendiente | pendiente | pendiente | pendiente |
| 4 | pendiente | pendiente | pendiente | pendiente |
| 8 | pendiente | pendiente | pendiente | pendiente |

Discutir el limite con la ley de Amdahl y medir CPU, memoria, I/O, red y Docker daemon.

## Tolerancia a fallos

En `/cluster/status`, `last_election_ms` es la duracion de la eleccion y
`last_failover_ms` mide desde que un nodo detecta que el lider no responde hasta
que acepta/anuncia al nuevo coordinador. Para medir el tiempo desde la caida
real, registrar tambien el instante en que se detiene el contenedor, ya que el
nodo puede tardar hasta un intervalo de heartbeat en detectar la perdida.

El coordinador consulta carga y estado de nodos al asignar tareas, e intenta
otro nodo si un envio falla. La cola y el registro son en memoria: no se afirma
que las tareas pendientes sobrevivan al reinicio de un nodo. Un timeout
tampoco permite saber siempre si el trabajo remoto llego a ejecutarse; el
reintento puede duplicar trabajo no idempotente.

## Herramientas de IA y conclusiones

Documentar herramientas utilizadas, asistencia recibida, decisiones verificadas y conclusiones de las mediciones.

## Limitaciones conocidas (Hit 3)

- Ventana sin líder: hasta ~1 heartbeat más la elección, con 502 al cliente y reintento de su parte.
- Tareas con error: se reintentan en todos los nodos antes de fallar, ya que un 502 remoto cuenta como falla del nodo.
- Carga desactualizada: la carga se lee de `/health`, así que tareas simultáneas pueden caer en el mismo nodo.
