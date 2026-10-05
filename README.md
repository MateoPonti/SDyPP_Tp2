# TP2 - Sistemas Distribuidos y Concurrencia

Implementacion en Python de los tres hits del Trabajo Practico 2. La lectura
recomendada es seguir los README de cada hit en orden.

## Estructura

- `hit1/`: tareas remotas en contenedores Docker.
- `hit2/`: pool de workers, cola concurrente, Lamport y benchmark.
- `hit3/`: nginx, multiples nodos y eleccion Bully.
- `hit3/scheduler.py`: asignacion de tareas por carga desde el coordinador.
- `shared/`: componentes realmente compartidos: modelos, configuración, logs y reloj de Lamport.
- `task_service/`: servicio HTTP empaquetable como imagen Docker.
- `tests/`: pruebas unitarias y de integracion HTTP.
- `docs/informe.md`: tabla de metricas y secciones para completar con mediciones.

## Ejecutar localmente

```powershell
Copy-Item .env.example .env
$env:EXECUTOR = "local"
python -m uvicorn hit1.server:app --reload
python client.py --calculation add 2 5
```

## Ejecutar con Docker y dos nodos

```powershell
docker compose up --build
python client.py --server http://localhost:8000 --calculation multiply 3 4
```

El endpoint `GET /health` devuelve el estado del servicio, nodo, lider, cola y workers. En Hit 3, las solicitudes recibidas por un seguidor se envian al coordinador, que consulta la carga de los nodos disponibles y asigna la tarea. Las credenciales de Docker nunca forman parte del JSON: el host debe estar autenticado previamente mediante Docker credential helper, token de corta duracion u OIDC del proveedor cloud.

## Que implementa cada hit

| Hit | Entrada principal | Implementacion propia |
| --- | --- | --- |
| 1 | `hit1.server:app` | Ejecutor Docker, servicio tarea y endpoint remoto. |
| 2 | `hit2.server:app` | Pool limitado, cola FIFO y Lamport. |
| 3 | `hit3.server:app` | Eleccion Bully, registro observado de nodos, asignacion por carga y reintento ante errores. |

## Pruebas

```powershell
python -m pip install -e ".[test]"
python -m pytest -q
```

## Benchmark

Con el servidor en modo local, repetir para `1`, `2`, `4` y `8` workers:

```powershell
$env:WORKERS = "4"
python -m uvicorn hit2.server:app
python hit2/benchmark.py --workers 4 --tasks 100
```

Los resultados deben copiarse a `docs/informe.md` y acompañarse con una gráfica.
