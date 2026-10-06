import time
import math
import serial
import threading
from gpiozero import Button, OutputDevice

# --- RS485 ---
PORT='/dev/ttyUSB0'
SLAVE_ID=1
SERVO_ID=2

BAUD_ZLTECH=115200
BAUD_SERVO=9600

# --- LLANTAS ---
DIAMETRO_RUEDA_M=0.254
PPR=16384
CIRCUNFERENCIA=math.pi*DIAMETRO_RUEDA_M
PULSOS_POR_METRO=PPR/CIRCUNFERENCIA
DISTANCIA_MOVIMIENTO=0.1
RAMPA_MS=500
VEL_RPM=30

# --- BROCAS ---
SERVO_RPM=500
TIEMPO_BROCAS=5

# --- GPIO ---
PIN_PULSADOR_INICIO=17
PIN_PULSADOR_DETENER=27
PIN_PARADA_EMERGENCIA=22
PIN_RELE_EMERGENCIA=10

ejecutando_secuencia=False
detener_solicitado=False
ser_global=None
rele_emergencia=None

def crc(data):
    c=0xFFFF
    for x in data:
        c^=x
        for _ in range(8):
            c=(c>>1)^0xA001 if c&1 else c>>1
    return c.to_bytes(2,'little')

def rtu(trama):
    ser_global.write(trama+crc(trama))
    time.sleep(0.05)

def lrc(data):
    return (-sum(data))&255

def ascii_write(addr,value):
    d=bytes([SERVO_ID,6,addr>>8,addr&255,value>>8,value&255])
    f=b":"+d.hex().upper().encode()+f"{lrc(d):02X}".encode()+b"\r\n"
    ser_global.write(f)
    time.sleep(0.1)

def int_a_4bytes(n):
    b=n.to_bytes(4,'big',signed=True)
    return b[:2],b[2:]

def cambiar_baudrate(baud):
    ser_global.baudrate=baud
    time.sleep(0.05)

# --- ZLTECH ---

def detener_motores():
    cambiar_baudrate(BAUD_ZLTECH)
    rtu(bytearray([SLAVE_ID,6,0x20,0x0E,0,7]))

def limpiar_errores():
    cambiar_baudrate(BAUD_ZLTECH)
    rtu(bytearray([SLAVE_ID,6,0x20,0x0E,0,6]))

def mover_robot_recto(metros):
    global detener_solicitado

    if detener_solicitado:
        return False

    cambiar_baudrate(BAUD_ZLTECH)

    pulsos=int(metros*PULSOS_POR_METRO)
    h_izq,l_izq=int_a_4bytes(pulsos)
    h_der,l_der=int_a_4bytes(-pulsos)

    rtu(bytearray([SLAVE_ID,6,0x20,0x0F,0,1]))
    rtu(bytearray([SLAVE_ID,6,0x20,0x0D,0,1]))

    r_bytes=RAMPA_MS.to_bytes(2,'big')
    for reg in [0x80,0x81,0x82,0x83]:
        rtu(bytearray([SLAVE_ID,6,0x20,reg])+r_bytes)

    v_bytes=VEL_RPM.to_bytes(2,'big')
    rtu(bytearray([SLAVE_ID,6,0x20,0x8E])+v_bytes)
    rtu(bytearray([SLAVE_ID,6,0x20,0x8F])+v_bytes)

    rtu(bytearray([SLAVE_ID,6,0x20,0x0E,0,8]))
    time.sleep(0.1)

    trama=bytearray([SLAVE_ID,0x10,0x20,0x8A,0,4,8])
    trama+=h_izq+l_izq+h_der+l_der
    rtu(trama)

    rtu(bytearray([SLAVE_ID,6,0x20,0x0E,0,0x10]))

    tiempo=(abs(metros)/(CIRCUNFERENCIA*(VEL_RPM/60)))+(RAMPA_MS/1000)+0.5
    inicio=time.time()

    while time.time()-inicio<tiempo:
        if detener_solicitado:
            detener_motores()
            return False
        time.sleep(0.05)

    return True

# --- SERVO BROCAS ---

def arrancar_brocas():
    cambiar_baudrate(BAUD_SERVO)

    # Pn305 debe estar configurado en 500 RPM
    # 1023h = Servo ON
    # 1024h = JOG adelante
    ascii_write(0x1023,1)
    time.sleep(0.2)
    ascii_write(0x1024,1)

def detener_brocas():
    cambiar_baudrate(BAUD_SERVO)

    # Detener JOG y Servo OFF
    ascii_write(0x1024,0)
    time.sleep(0.2)
    ascii_write(0x1023,0)

def rutina_perforacion():
    global ejecutando_secuencia,detener_solicitado

    limpiar_errores()
    time.sleep(0.1)

    while ejecutando_secuencia and not detener_solicitado:

        # 1. Avanzar 0.1 m
        if not mover_robot_recto(DISTANCIA_MOVIMIENTO):
            break

        # 2. Encender brocas durante 5 segundos
        arrancar_brocas()

        inicio=time.time()
        while time.time()-inicio<TIEMPO_BROCAS:
            if detener_solicitado:
                break
            time.sleep(0.05)

        # 3. Detener brocas
        detener_brocas()

        if detener_solicitado:
            break

    detener_brocas()
    detener_motores()

    ejecutando_secuencia=False
    print("\n--- Secuencia finalizada/detenida ---")

# --- BOTONES ---

def presionar_inicio():
    global ejecutando_secuencia,detener_solicitado

    if not rele_emergencia or rele_emergencia.is_false:
        print("\n[!] No se puede iniciar: emergencia activada.")
        return

    if not ejecutando_secuencia:
        detener_solicitado=False
        ejecutando_secuencia=True
        print("\n[>] Iniciando secuencia...")
        threading.Thread(target=rutina_perforacion,daemon=True).start()
    else:
        print("\n[!] La secuencia ya está en ejecución.")

def presionar_detener():
    global ejecutando_secuencia,detener_solicitado

    print("\n[>] Deteniendo secuencia...")
    detener_solicitado=True
    ejecutando_secuencia=False

    if ser_global:
        detener_brocas()
        detener_motores()

def parada_emergencia_activada():
    global ejecutando_secuencia,detener_solicitado

    print("\n[!] PARADA DE EMERGENCIA")
    detener_solicitado=True
    ejecutando_secuencia=False

    if ser_global:
        detener_brocas()
        detener_motores()

    if rele_emergencia:
        rele_emergencia.off()

def parada_emergencia_liberada():
    if rele_emergencia:
        rele_emergencia.on()

def main():
    global ser_global,rele_emergencia

    btn_inicio=Button(PIN_PULSADOR_INICIO,pull_up=True,bounce_time=0.1)
    btn_detener=Button(PIN_PULSADOR_DETENER,pull_up=True,bounce_time=0.1)
    btn_emergencia=Button(PIN_PARADA_EMERGENCIA,pull_up=True,bounce_time=0.05)

    rele_emergencia=OutputDevice(
        PIN_RELE_EMERGENCIA,
        active_high=True,
        initial_value=False
    )

    btn_inicio.when_pressed=presionar_inicio
    btn_detener.when_pressed=presionar_detener
    btn_emergencia.when_released=parada_emergencia_activada
    btn_emergencia.when_pressed=parada_emergencia_liberada

    try:
        ser_global=serial.Serial(
            PORT,
            BAUD_ZLTECH,
            timeout=1
        )

        print("=== CONTROL DE MAQUINA ===")
        print("RS485:",PORT)
        print("Esclavo 1: ZLTECH - 115200 RTU")
        print("Esclavo 2: ESTUN - 9600 8O1 ASCII")
        print("Movimiento:",DISTANCIA_MOVIMIENTO,"m")
        print("Brocas:",SERVO_RPM,"RPM /",TIEMPO_BROCAS,"s")
        print("GPIO 17: INICIO")
        print("GPIO 27: DETENER")
        print("GPIO 22: EMERGENCIA")

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nSaliendo...")

    except Exception as e:
        print("\nError:",e)

    finally:
        if ser_global and ser_global.is_open:
            try:
                detener_brocas()
                detener_motores()
            except:
                pass
            ser_global.close()

        if rele_emergencia:
            rele_emergencia.off()
            rele_emergencia.close()

if __name__=="__main__":
    main()
