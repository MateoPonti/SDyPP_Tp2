# HIT 3 - Coordinacion, balanceo y tolerancia a fallos

## Objetivo

Ejecutar varios servidores detras de nginx. Los nodos eligen coordinador con
Bully; el coordinador observa su carga y distribuye las tareas entre nodos
disponibles.

## Protocolo Bully

1. Al arrancar, cada nodo espera `STARTUP_DELAY`.
2. Un nodo envia `ELECTION` a sus pares con ID mayor.
3. Un nodo mayor responde `OK` e inicia su propia eleccion.
4. Si ningun nodo mayor responde, el candidato se proclama coordinador y envia
   `COORDINATOR` a los pares.
5. Los seguidores comprueban al coordinador cada `HEARTBEAT_INTERVAL` segundos.
   Si no responde, inician una eleccion.
6. Un nodo rechaza el anuncio de coordinador con un ID inferior al propio e
   inicia una eleccion.

`PEERS` usa una lista de pares `ID=URL`, separada por comas. Por ejemplo:
`2=http://server-2:8000`.

## Asignacion de tareas

- Un cliente puede enviar `POST /getRemoteTask` a nginx o directamente a
  cualquiera de los nodos.
- Si la solicitud llega a un seguidor, este la reenvia al coordinador mediante
  `/cluster/dispatch`.
- El coordinador consulta `/health` de cada peer configurado y agrega su propia
  cola y workers. Registra el estado observado, cantidad de tareas en cola,
  workers ocupados y ultima vez visto.
- Asigna la tarea al nodo disponible con menor carga (`queue_size +
  active_workers`). Si la ejecucion remota falla, intenta otro candidato.
- `/cluster/execute` es la ruta interna para pedir a un nodo que ejecute una
  tarea en su pool local.

El registro de nodos vive en memoria en el coordinador y se actualiza al
asignar tareas; no es almacenamiento durable.

## Estado y mediciones

- `GET /health`: estado del servicio, nodo, coordinador, cola y workers.
- `GET /cluster/status`: identificador del nodo, coordinador, ultimos tiempos
  de eleccion/failover y el registro de nodos observado por el coordinador.
- `last_election_ms` mide solo la eleccion.
- `last_failover_ms` mide desde la deteccion de la caida hasta aceptar/anunciar
  al nuevo coordinador. No incluye el tiempo entre la caida real y el siguiente
  heartbeat.

Reducir `HEARTBEAT_INTERVAL` puede acelerar la deteccion, pero aumenta el
trafico. `STARTUP_DELAY` da tiempo a que los pares inicien antes de la primera
eleccion.

## Ejecucion con Docker Compose

```powershell
docker compose up --build
```

Consultar `http://localhost:8000/health`, y los endpoints `/cluster/status` en
cada servidor para ver coordinador y registro. Compose configura dos nodos,
cada uno con el ID y URL de su par.

## Ejecucion manual de dos procesos

Abrir dos terminales desde la raiz del proyecto.

Terminal 1:

```powershell
$env:NODE_ID = "1"
$env:PEERS = "2=http://localhost:8002"
$env:STARTUP_DELAY = "1"
python -m uvicorn hit3.server:app --port 8001
```

Terminal 2:

```powershell
$env:NODE_ID = "2"
$env:PEERS = "1=http://localhost:8001"
$env:STARTUP_DELAY = "1"
python -m uvicorn hit3.server:app --port 8002
```

Para simular una falla, detener el proceso que sea coordinador y observar la
nueva eleccion en los logs y en `/cluster/status`.

## Limitaciones importantes

- Las colas y el registro viven en memoria. Al reiniciar un proceso se pierden.
- Un timeout de red no permite saber con certeza si el nodo alcanzo a ejecutar
  la tarea. El coordinador puede reintentar en otro nodo; eso da semantica de
  mejor esfuerzo/como minimo un intento y puede duplicar trabajo si las tareas
  dejan de ser operaciones puras. Para garantias se necesita idempotencia y/o
  una cola durable con estado compartido.
- No existe replicacion durable de tareas pendientes. Una tarea en curso en un
  nodo caido puede requerir reintento del cliente.
- Las pruebas unitarias simulan la red en memoria. La medicion de recuperacion
  real requiere levantar Compose, detener el lider y medir desde el instante
  de la caida.

### Limitaciones adicionales (comportamiento observado en el diseño)

- **Ventana sin líder:** si el coordinador cae, hay una ventana de hasta un intervalo de
  heartbeat (`HEARTBEAT_INTERVAL`, 1 s por defecto) más el tiempo de elección en la que un
  seguidor aún reenvía al líder caído. En ese lapso el cliente recibe `502` y debe reintentar.
- **Tareas que fallan:** un error remoto de una tarea (por ejemplo, 502 del nodo) se trata
  como falla del nodo, por lo que el coordinador reintenta en los demás nodos. Una tarea que
  falla siempre se intenta en todos los nodos antes de devolver error.
- **Carga desactualizada:** el coordinador mide la carga con `GET /health` (cola + workers
  activos) justo antes de asignar. Varias tareas simultáneas pueden ver la misma carga y
  asignarse al mismo nodo. Una mejora posible es contar localmente las tareas en vuelo por nodo.
