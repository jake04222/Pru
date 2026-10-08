import time
import math
import serial
import RPi.GPIO as GPIO

PORT='/dev/ttyUSB0'

# ZLTECH
SLAVE_ID=1
BAUD_ZLTECH=115200

# ESTUN
SERVO_ID=2
BAUD_SERVO=9600

# GPIO
GPIO_START=17
GPIO_STOP=27
GPIO_EMERGENCY=22
GPIO_EMERGENCY_OUT=10
GPIO_ACTUADOR=9
GPIO_FIN_CARRERA=11

GPIO.setmode(GPIO.BCM)
GPIO.setup(GPIO_START,GPIO.IN,pull_up_down=GPIO.PUD_UP)
GPIO.setup(GPIO_STOP,GPIO.IN,pull_up_down=GPIO.PUD_UP)
GPIO.setup(GPIO_EMERGENCY,GPIO.IN,pull_up_down=GPIO.PUD_UP)
GPIO.setup(GPIO_FIN_CARRERA,GPIO.IN,pull_up_down=GPIO.PUD_UP)

GPIO.setup(GPIO_EMERGENCY_OUT,GPIO.OUT,initial=GPIO.HIGH)

# GPIO9: rele activo LOW
GPIO.setup(GPIO_ACTUADOR,GPIO.OUT,initial=GPIO.HIGH)

# Tiempos
TIEMPO_ESPERA_BROCAS=0.3
TIEMPO_ACTUADOR=0.5
TIEMPO_RETORNO=1.5

# Llantas
DIAMETRO_RUEDA_M=0.254
PPR=16384
CIRCUNFERENCIA=math.pi*DIAMETRO_RUEDA_M
PULSOS_POR_METRO=PPR/CIRCUNFERENCIA
DISTANCIA_MOVIMIENTO=0.1
RAMPA_MS=500
VEL_RPM=30

ser=None
estado='PARADA'
emergencia_activa=False

def abrir_puerto(baudrate,parity='N'):
    global ser

    if ser and ser.is_open:
        ser.close()
        time.sleep(0.05)

    ser=serial.Serial(
        PORT,
        baudrate,
        bytesize=8,
        parity=parity,
        stopbits=1,
        timeout=0.3
    )

    time.sleep(0.1)
    ser.reset_input_buffer()
    ser.reset_output_buffer()

def crc(data):
    c=0xFFFF

    for x in data:
        c^=x

        for _ in range(8):
            c=(c>>1)^0xA001 if c&1 else c>>1

    return c.to_bytes(2,'little')

def rtu(data):
    ser.write(data+crc(data))
    ser.flush()
    time.sleep(0.05)

def lrc(data):
    return (-sum(data))&255

def ascii_write(reg,val):
    d=bytes([
        SERVO_ID,6,
        reg>>8,reg&255,
        val>>8,val&255
    ])

    f=b":"+d.hex().upper().encode()
    f+=f"{lrc(d):02X}".encode()+b"\r\n"

    ser.write(f)
    ser.flush()
    time.sleep(0.1)

    return bool(ser.read(50))

def int_a_4bytes(n):
    b=n.to_bytes(4,'big',signed=True)
    return b[:2],b[2:]

# LLANTAS

def arrancar_llantas():
    abrir_puerto(BAUD_ZLTECH)

    pulsos=int(DISTANCIA_MOVIMIENTO*PULSOS_POR_METRO)

    h1,l1=int_a_4bytes(pulsos)
    h2,l2=int_a_4bytes(-pulsos)

    rtu(bytearray([SLAVE_ID,6,0x20,0x0F,0,1]))
    rtu(bytearray([SLAVE_ID,6,0x20,0x0D,0,1]))

    r=RAMPA_MS.to_bytes(2,'big')

    for reg in [0x80,0x81,0x82,0x83]:
        rtu(bytearray([SLAVE_ID,6,0x20,reg])+r)

    v=VEL_RPM.to_bytes(2,'big')

    rtu(bytearray([SLAVE_ID,6,0x20,0x8E])+v)
    rtu(bytearray([SLAVE_ID,6,0x20,0x8F])+v)

    rtu(bytearray([SLAVE_ID,6,0x20,0x0E,0,8]))

    trama=bytearray([
        SLAVE_ID,0x10,
        0x20,0x8A,
        0,4,8
    ])

    trama+=h1+l1+h2+l2

    rtu(trama)

    rtu(bytearray([
        SLAVE_ID,6,
        0x20,0x0E,
        0,0x10
    ]))

    print("LLANTAS -> 10 CM")

def frenar_llantas():
    abrir_puerto(BAUD_ZLTECH)

    rtu(bytearray([
        SLAVE_ID,6,
        0x20,0x0E,
        0,7
    ]))

    print("LLANTAS -> PARADAS")

# ESTUN

def arrancar_brocas():
    abrir_puerto(BAUD_SERVO,'O')

    if not ascii_write(0x1023,1):
        print("ERROR ESTUN")
        return False

    time.sleep(0.1)

    if not ascii_write(0x1024,1):
        print("ERROR JOG")
        return False

    print("BROCAS -> ON")
    return True

def frenar_brocas():
    abrir_puerto(BAUD_SERVO,'O')

    ascii_write(0x1024,0)

    time.sleep(0.1)

    ascii_write(0x1023,0)

    print("BROCAS -> OFF")

# ACTUADOR

def activar_actuador():
    GPIO.output(GPIO_ACTUADOR,GPIO.LOW)
    print("ACTUADOR -> AVANZANDO")

def desactivar_actuador():
    GPIO.output(GPIO_ACTUADOR,GPIO.HIGH)
    print("ACTUADOR -> RETORNANDO")

# ENTRADAS

def leer_entradas():
    global emergencia_activa

    # GPIO22 NC
    # LOW = normal
    # HIGH = emergencia
    if GPIO.input(GPIO_EMERGENCY)==GPIO.HIGH:
        emergencia_activa=True
        return 'EMERGENCY'

    # GPIO17 = START
    if GPIO.input(GPIO_START)==GPIO.LOW:
        return 'START'

    # GPIO27 = STOP
    if GPIO.input(GPIO_STOP)==GPIO.LOW:
        return 'STOP'

    return None

# PARADA

def parar_maquina():
    desactivar_actuador()

    try:
        frenar_brocas()
    except:
        pass

    try:
        frenar_llantas()
    except:
        pass

# EMERGENCIA

def emergencia():
    global emergencia_activa,estado

    emergencia_activa=True
    estado='PARADA'

    print("\n!!! PARADA DE EMERGENCIA !!!")

    desactivar_actuador()

    try:
        frenar_brocas()
    except:
        pass

    try:
        frenar_llantas()
    except:
        pass

    GPIO.output(GPIO_EMERGENCY_OUT,GPIO.LOW)

    print("GPIO10 -> ACTIVADO")

# ESPERA CON ENTRADAS

def esperar(tiempo):
    inicio=time.time()

    while time.time()-inicio<tiempo:

        orden=leer_entradas()

        if orden=='STOP':
            print("PARO SOLICITADO")
            return 'STOP'

        if orden=='EMERGENCY':
            emergencia()
            return 'EMERGENCY'

        time.sleep(0.01)

    return None

# ESPERA FIN DE CARRERA

def esperar_fin_carrera():
    print("ESPERANDO GPIO11...")

    while True:

        orden=leer_entradas()

        if orden=='STOP':
            return 'STOP'

        if orden=='EMERGENCY':
            emergencia()
            return 'EMERGENCY'

        if GPIO.input(GPIO_FIN_CARRERA)==GPIO.HIGH:
            print("GPIO11 -> FIN DE CARRERA")
            return 'OK'

        time.sleep(0.01)

# CICLO

def ciclo():
    global estado,emergencia_activa

    estado='MARCHA'
    emergencia_activa=False

    GPIO.output(GPIO_EMERGENCY_OUT,GPIO.HIGH)
    desactivar_actuador()

    print("\n=== MAQUINA EN MARCHA ===")

    while estado=='MARCHA':

        # 1. AVANZAR 10 CM

        arrancar_llantas()

        tiempo_mov=DISTANCIA_MOVIMIENTO/(VEL_RPM*CIRCUNFERENCIA/60)

        orden=esperar(tiempo_mov)

        frenar_llantas()

        if orden=='STOP':
            estado='PARADA'
            break

        if orden=='EMERGENCY':
            break

        # 2. ESPERAR 0.3 SEGUNDOS

        print("ESPERA -> 0.3 S")

        orden=esperar(TIEMPO_ESPERA_BROCAS)

        if orden:
            estado='PARADA'
            break

        # 3. ENCENDER BROCAS

        if not arrancar_brocas():
            estado='PARADA'
            break

        # 4. ESPERAR 0.5 SEGUNDOS

        print("ESPERA BROCAS -> 0.5 S")

        orden=esperar(TIEMPO_ACTUADOR)

        if orden:
            frenar_brocas()
            estado='PARADA'
            break

        # 5. ACTIVAR ACTUADOR

        activar_actuador()

        # 6. ESPERAR FIN DE CARRERA GPIO11

        orden=esperar_fin_carrera()

        if orden:
            desactivar_actuador()
            frenar_brocas()
            estado='PARADA'
            break

        # 7. RETRAER ACTUADOR

        desactivar_actuador()

        # 8. PARAR BROCAS
        frenar_brocas()

        # 9. ESPERAR 1.5 SEGUNDOS

        print("ESPERA RETORNO ->",TIEMPO_RETORNO,"S")

        orden=esperar(TIEMPO_RETORNO)

        if orden:
            estado='PARADA'
            break

        print("=== REPITE CICLO ===")

    if not emergencia_activa:
        parar_maquina()

    print("\nMAQUINA DETENIDA")

# PRINCIPAL

def main():
    global estado

    print("=== CONTROL MAQUINA ===")
    print("GPIO17 = ARRANQUE")
    print("GPIO27 = PARO")
    print("GPIO22 = EMERGENCIA NC")
    print("GPIO10 = SALIDA EMERGENCIA")
    print("GPIO9  = ACTUADOR NEUMATICO")
    print("GPIO11 = FIN DE CARRERA")
    print("======================")

    try:

        while True:

            # EMERGENCIA SIEMPRE PRIMERO

            if GPIO.input(GPIO_EMERGENCY)==GPIO.HIGH:
                emergencia()
                time.sleep(0.1)
                continue

            orden=leer_entradas()

            if orden=='START' and estado=='PARADA':

                # Solo permite arrancar si no hay emergencia
                if GPIO.input(GPIO_EMERGENCY)==GPIO.LOW:
                    ciclo()

            elif orden=='STOP':

                estado='PARADA'
                parar_maquina()

            time.sleep(0.01)

    except KeyboardInterrupt:
        emergencia()

    except Exception as e:
        print("ERROR:",e)
        emergencia()

    finally:

        try:
            emergencia()
        except:
            pass

        GPIO.output(GPIO_ACTUADOR,GPIO.HIGH)
        GPIO.cleanup()

        if ser and ser.is_open:
            ser.close()

if __name__=="__main__":
    main()
