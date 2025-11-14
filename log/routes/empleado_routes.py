from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from flask_mysqldb import MySQL, MySQLdb
from MySQLdb import IntegrityError
import MySQLdb.cursors
from datetime import date, datetime
import json
from werkzeug.security import check_password_hash, generate_password_hash

from __init__ import mysql

empleado_bp = Blueprint('empleado', __name__)

# ===============================
# VERIFICACIÓN DE EMPLEADO
# ===============================
def verificar_empleado():
    """Función helper para verificar si el usuario es empleado"""
    if 'logueado' not in session:
        return False, '⚠️ Debes iniciar sesión primero'
    
    if session.get('rol') not in ['empleado', 'administrador']:
        return False, f'❌ Acceso denegado. Tu rol actual es: {session.get("rol")}'
    
    return True, None

# ===============================
# DASHBOARD EMPLEADO
# ===============================
@empleado_bp.route('/empleado/dashboard')
def empleado_dashboard():
    es_empleado, mensaje = verificar_empleado()
    if not es_empleado:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))
    
    return render_template('empleado.html')

# ===============================
# MESAS
# ===============================
@empleado_bp.route('/empleado/mesas')
def mesas_empleado():
    es_empleado, mensaje = verificar_empleado()
    if not es_empleado:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))
    
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM mesas ORDER BY numero_mesa ASC")
    mesas = cur.fetchall()
    cur.close()
    
    return render_template('mesas_empleado.html', mesas=mesas)

# ==================== ORDEN DE MESA ====================
@empleado_bp.route('/empleado/orden/<int:mesa_id>', methods=['GET', 'POST'])
def orden_mesa(mesa_id):
    es_empleado, mensaje = verificar_empleado()
    if not es_empleado:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    if request.method == 'POST':
        productos_json = request.form.get('productos', '[]')
        total = float(request.form.get('total', 0))

        try:
            productos = json.loads(productos_json)
        except json.JSONDecodeError:
            productos = []

        if len(productos) == 0 or total <= 0:
            flash("⚠️ No se seleccionaron productos válidos o el total es 0", "warning")
            return redirect(url_for('empleado.orden_mesa', mesa_id=mesa_id))

        # ✅ VALIDAR STOCK ANTES DE CONFIRMAR
        stock_insuficiente = []
        for p in productos:
            cur.execute("SELECT nombre, cantidad, estado FROM productos WHERE id_producto = %s", (p['id_producto'],))
            producto = cur.fetchone()
            
            if not producto:
                stock_insuficiente.append(f"ID {p['id_producto']} (no encontrado)")
            elif producto['estado'] != 'Disponible':
                stock_insuficiente.append(f"{producto['nombre']} (no disponible)")
            elif producto['cantidad'] < p['cantidad']:
                stock_insuficiente.append(f"{producto['nombre']} (solo quedan {producto['cantidad']} unidades)")
        
        if stock_insuficiente:
            flash(f"❌ Stock insuficiente: {', '.join(stock_insuficiente)}", "danger")
            cur.close()
            return redirect(url_for('empleado.orden_mesa', mesa_id=mesa_id))

        try:
            fecha = datetime.now().date()
            hora = datetime.now().strftime("%H:%M:%S")

            # Insertar pago
            cur.execute("""
                INSERT INTO pagos_restaurante (id_mesa, fecha, hora, total)
                VALUES (%s, %s, %s, %s)
            """, (mesa_id, fecha, hora, total))
            id_pago_restaurante = cur.lastrowid

            # Insertar productos y reducir stock
            for p in productos:
                cur.execute("""
                    INSERT INTO detalle_pedido_restaurante 
                    (id_pago_restaurante, id_producto_em, cantidad, precio_unitario)
                    VALUES (%s, %s, %s, %s)
                """, (
                    id_pago_restaurante,
                    p['id_producto'],
                    p['cantidad'],
                    p['precio']
                ))
                
                # ✅ REDUCIR STOCK
                cur.execute("""
                    UPDATE productos 
                    SET cantidad = cantidad - %s 
                    WHERE id_producto = %s
                """, (p['cantidad'], p['id_producto']))

            mysql.connection.commit()
            cur.close()

            flash(f"✅ Pago registrado correctamente. Mesa {mesa_id} - Total: ${total:,.0f}", "success")
            return redirect(url_for('empleado.mesas_empleado'))
            
        except Exception as e:
            mysql.connection.rollback()
            flash(f"❌ Error al registrar pago: {str(e)}", "danger")
            print(f"Error: {e}")
            return redirect(url_for('empleado.orden_mesa', mesa_id=mesa_id))

    # ✅ Solo productos disponibles con stock
    cur.execute("SELECT * FROM categorias WHERE id_categoria != 6")
    categorias = cur.fetchall()
    cur.execute("""
        SELECT * FROM productos 
        WHERE cod_categoria != 6 
        AND estado = 'Disponible' 
        AND cantidad > 0
    """)
    productos = cur.fetchall()
    cur.close()
    return render_template('calculadora.html', mesa=mesa_id, categorias=categorias, productos=productos)

@empleado_bp.route('/empleado/historial_pagos', methods=['GET'])
def historial_pagos_restaurante():
    es_empleado, mensaje = verificar_empleado()
    if not es_empleado:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))

    cur = mysql.connection.cursor()
    query = request.args.get("query", "").strip()

    if query:
        cur.execute("""
            SELECT * FROM pagos_restaurante
            WHERE CAST(id_pago_restaurante AS CHAR) LIKE %s
               OR DATE_FORMAT(fecha, '%%Y-%%m-%%d') LIKE %s
               OR hora LIKE %s
            ORDER BY fecha DESC, hora DESC
        """, (f"%{query}%", f"%{query}%", f"%{query}%"))
    else:
        cur.execute("SELECT * FROM pagos_restaurante ORDER BY fecha DESC, hora DESC")

    pagos = cur.fetchall()

    historial_por_fecha = {}

    for pago in pagos:
        cur.execute("""
            SELECT d.*, p.nombre
            FROM detalle_pedido_restaurante d
            JOIN productos p ON d.id_producto = p.id_producto
            WHERE d.id_pago_restaurante = %s
        """, (pago["id_pago_restaurante"],))
        detalles = cur.fetchall()

        pago["detalles"] = detalles

        fecha = pago["fecha"].strftime("%Y-%m-%d")
        if fecha not in historial_por_fecha:
            historial_por_fecha[fecha] = []
        historial_por_fecha[fecha].append(pago)

    cur.close()
    return render_template(
        'historial_pagos_restaurante.html',
        historial_por_fecha=historial_por_fecha,
        historial=pagos
    )

    cur.close()
    return render_template('historial_pagos_restaurante.html', historial=historial)

# ===============================
# REGISTRAR PEDIDO
# ===============================
@empleado_bp.route('/empleado/registrar', methods=['GET', 'POST'])
def registrar_pedido():
    es_empleado, mensaje = verificar_empleado()
    if not es_empleado:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        flash("✅ Pedido registrado correctamente", "success")
        return redirect(url_for('empleado.ordenes_empleado'))
    
    cur = mysql.connection.cursor()

    # Obtener categorías
    cur.execute("SELECT id_categoria, nombre_categoria FROM categorias ORDER BY nombre_categoria")
    categorias_raw = cur.fetchall()

    categorias = []
    for c in categorias_raw:
        if isinstance(c, dict):
            categorias.append({
                'id_categoria': c.get('id_categoria'),
                'nombre_categoria': c.get('nombre_categoria')
            })
        else:
            categorias.append({
                'id_categoria': c[0],
                'nombre_categoria': c[1]
            })

    # ✅ Solo productos disponibles con stock
    cur.execute("""
        SELECT 
            p.id_producto, 
            p.nombre, 
            p.precio, 
            p.cod_categoria AS id_categoria, 
            p.estado,
            p.cantidad,
            c.nombre_categoria
        FROM productos p
        LEFT JOIN categorias c ON p.cod_categoria = c.id_categoria
        WHERE p.estado = 'Disponible' AND p.cantidad > 0
        ORDER BY c.nombre_categoria, p.nombre
    """)
    productos_raw = cur.fetchall()

    productos = []
    for p in productos_raw:
        if isinstance(p, dict):
            productos.append({
                'id_producto': p.get('id_producto'),
                'nombre': p.get('nombre'),
                'precio': p.get('precio'),
                'id_categoria': p.get('id_categoria'),
                'nombre_categoria': p.get('nombre_categoria'),
                'estado': p.get('estado', 'Disponible'),
                'cantidad': p.get('cantidad', 0)
            })
        else:
            productos.append({
                'id_producto': p[0],
                'nombre': p[1],
                'precio': p[2],
                'id_categoria': p[3],
                'estado': p[4] if len(p) > 4 else 'Disponible',
                'cantidad': p[5] if len(p) > 5 else 0,
                'nombre_categoria': p[6] if len(p) > 6 else ''
            })

    cur.close()

    return render_template("registrar_empleado.html", productos=productos, categorias=categorias)

# ===============================
# ACTUALIZAR ESTADO PRODUCTO
# ===============================
@empleado_bp.route("/empleado/actualizar_estado_producto", methods=["POST"])
def actualizar_estado_producto():
    data = request.get_json()
    id_producto = data.get("id_producto")
    nuevo_estado = data.get("estado")

    if not id_producto or not nuevo_estado:
        return jsonify({"success": False, "msg": "⚠️ Datos incompletos"}), 400

    try:
        cur = mysql.connection.cursor()
        
        cur.execute("SELECT nombre FROM productos WHERE id_producto = %s", (id_producto,))
        producto = cur.fetchone()
        
        if not producto:
            return jsonify({"success": False, "msg": "⚠️ Producto no encontrado"}), 404
        
        cur.execute("""
            UPDATE productos SET estado = %s WHERE id_producto = %s
        """, (nuevo_estado, id_producto))
        mysql.connection.commit()
        cur.close()
        
        return jsonify({
            "success": True, 
            "msg": f"✅ {producto['nombre']} marcado como {nuevo_estado}",
            "nuevo_estado": nuevo_estado
        })
        
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({"success": False, "msg": f"❌ Error: {str(e)}"}), 500

# ===============================
# ÓRDENES
# ===============================
@empleado_bp.route('/empleado/ordenes')
def ordenes_empleado():
    es_empleado, mensaje = verificar_empleado()
    if not es_empleado:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))
    
    search_query = request.args.get('search_query', '').strip()

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    if search_query:
        cur.execute("""
            SELECT * FROM pedidos
            WHERE (cod_usuario LIKE %s OR telefono LIKE %s OR estado LIKE %s)
            AND estado IN ('pendiente', 'entregado')
            ORDER BY fecha DESC, hora DESC
        """, (f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"))
    else:
        cur.execute("""
            SELECT * FROM pedidos
            WHERE estado IN ('pendiente', 'entregado')
            ORDER BY fecha DESC, hora DESC
        """)
    
    pedidos = cur.fetchall()
    ordenes = []

    for pedido in pedidos:
        cur.execute("""
            SELECT dp.cod_producto, dp.cantidad, dp.precio_unitario, p.nombre
            FROM detalle_pedido dp
            JOIN productos p ON dp.cod_producto = p.id_producto
            WHERE dp.cod_pedido = %s
        """, (pedido['id_pedido'],))
        detalles = cur.fetchall()

        productos = []
        for d in detalles:
            subtotal = float(d['cantidad']) * float(d['precio_unitario'])
            productos.append({
                'nombre': d['nombre'],
                'cantidad': d['cantidad'],
                'precio_unitario': float(d['precio_unitario']),
                'subtotal': subtotal
            })

        pedido['productos'] = productos
        ordenes.append(pedido)

    cur.close()
    
    return render_template('ordenes_empleado.html', ordenes=ordenes, search_query=search_query)


# ===============================
# CAMBIAR ESTADO PEDIDO (AJAX)
# ===============================
@empleado_bp.route('/actualizar_estado/<int:id_pedido>', methods=['POST'])
def actualizar_estado(id_pedido):
    es_empleado, mensaje = verificar_empleado()
    if not es_empleado:
        return jsonify({'error': mensaje}), 403

    data = request.get_json()
    nuevo_estado = data.get('estado')

    cur = mysql.connection.cursor()
    cur.execute("UPDATE pedidos SET estado=%s WHERE id_pedido=%s", (nuevo_estado, id_pedido))
    mysql.connection.commit()
    cur.close()

    estado_emoji = {
        'pendiente': '⏳',
        'entregado': '✅',
        'cancelado': '❌'
    }.get(nuevo_estado, '📦')

    return jsonify({
        'success': True, 
        'estado': nuevo_estado,
        'mensaje': f'{estado_emoji} Pedido #{id_pedido} marcado como {nuevo_estado}'
    })
    
#historial ordenes 
@empleado_bp.route('/empleado/historial_ordenes')
def historial_ordenes_empleado():
    es_empleado, mensaje = verificar_empleado()
    if not es_empleado:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    search_query = request.args.get('query', '').strip()

    # ========================================
    # CONSULTA BASE CON JOIN A USUARIOS
    # ========================================
    sql = """
        SELECT 
            p.*, 
            u.nombre AS nombre_usuario,
            u.telefono AS telefono_usuario
        FROM pedidos p
        JOIN usuarios u ON p.cod_usuario = u.id_usuario
        WHERE p.estado IN ('entregado', 'cancelado')
    """

    params = []

    # =======================================
    # BÚSQUEDA
    # =======================================
    if search_query:
        sql += """
            AND (
                u.nombre LIKE %s OR
                u.telefono LIKE %s OR
                p.estado LIKE %s
            )
        """
        params.extend([
            f"%{search_query}%",
            f"%{search_query}%",
            f"%{search_query}%"
        ])

    sql += " ORDER BY p.fecha DESC, p.hora DESC"

    cur.execute(sql, params)
    pedidos = cur.fetchall()

    ordenes = []

    # =======================================
    # BUSCAR DETALLES DE CADA ORDEN
    # =======================================
    for pedido in pedidos:
        cur.execute("""
            SELECT dp.cod_producto, dp.cantidad, dp.precio_unitario, p.nombre
            FROM detalle_pedido dp
            JOIN productos p ON dp.cod_producto = p.id_producto
            WHERE dp.cod_pedido = %s
        """, (pedido['id_pedido'],))

        detalles = cur.fetchall()

        productos = []
        for d in detalles:
            subtotal = float(d['cantidad']) * float(d['precio_unitario'])
            productos.append({
                'nombre': d['nombre'],
                'cantidad': d['cantidad'],
                'precio_unitario': float(d['precio_unitario']),
                'subtotal': subtotal
            })

        # Datos corregidos
        pedido['nombre'] = pedido['nombre_usuario']
        pedido['telefono'] = pedido['telefono_usuario']
        pedido['productos'] = productos

        ordenes.append(pedido)

    # =======================================
    # AGRUPAR POR FECHA
    # =======================================
    meses = {
        '01': 'Enero', '02': 'Febrero', '03': 'Marzo', '04': 'Abril',
        '05': 'Mayo', '06': 'Junio', '07': 'Julio', '08': 'Agosto',
        '09': 'Septiembre', '10': 'Octubre', '11': 'Noviembre', '12': 'Diciembre'
    }

    ordenes_por_fecha = {}

    for o in ordenes:
        fecha = str(o['fecha'])  # formato YYYY-MM-DD
        anio = fecha[:4]
        mes = fecha[5:7]
        dia = fecha[8:10]

        fecha_bonita = f"{dia} {meses[mes]} {anio}"

        if fecha_bonita not in ordenes_por_fecha:
            ordenes_por_fecha[fecha_bonita] = {
                "lista": [],
                "total_dinero": 0
            }

        ordenes_por_fecha[fecha_bonita]["lista"].append(o)

        # suma dinero (salta cancelados)
        if o['estado'] != 'cancelado':
            ordenes_por_fecha[fecha_bonita]["total_dinero"] += float(o['total'])

    cur.close()

    return render_template(
        'historial_ordenes_em.html',
        ordenes_por_fecha=ordenes_por_fecha,
        query=search_query
    )


# ===============================
# RESERVAS
# ===============================
@empleado_bp.route('/empleado/reservas')
def reservas_empleado():
    es_empleado, mensaje = verificar_empleado()
    if not es_empleado:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))
    
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT * FROM reservas
        WHERE estado IN ('Pendiente', 'Confirmada')
        ORDER BY fecha ASC, hora ASC
    """)
    reservas = cur.fetchall()
    cur.close()
    
    today = str(date.today())
    return render_template('reservas_empleado.html', reservas=reservas, today=today)

# ===============================
# BUSCAR RESERVAS
# ===============================
@empleado_bp.route('/empleado/buscar_reservas')
def buscar_reservas():
    es_empleado, mensaje = verificar_empleado()
    if not es_empleado:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))
    
    search_query = request.args.get('search_query', '')
    
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT * FROM reservas
        WHERE (nombre LIKE %s OR documento LIKE %s OR telefono LIKE %s)
        AND estado IN ('Pendiente', 'Confirmada')
        ORDER BY fecha ASC, hora ASC
    """, (f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'))
    reservas = cur.fetchall()
    cur.close()
    
    today = str(date.today())
    return render_template('reservas_empleado.html', reservas=reservas, today=today)

# ===============================
# AGREGAR RESERVA
# ===============================
@empleado_bp.route('/empleado/agregar_reserva', methods=['POST'])
def agregar_reserva():
    fecha = request.form["fecha"]
    nombre = request.form["nombre"]

    cur = mysql.connection.cursor()

    # Validar reserva duplicada
    cur.execute("SELECT COUNT(*) as total FROM reservas WHERE fecha = %s", (fecha,))
    result = cur.fetchone()
    count = result['total'] if result else 0

    if count > 0:
        flash(f"⚠️ Ya existe una reserva para el {fecha}", "warning")
        cur.close()
        return redirect(url_for("empleado.reservas_empleado"))

    # Validar usuario
    id_usuario = request.form["id_usuario"]
    cur.execute("SELECT id_usuario FROM usuarios WHERE id_usuario = %s", (id_usuario,))
    usuario = cur.fetchone()
    
    if not usuario:
        flash(f"❌ El usuario con ID {id_usuario} no existe", "danger")
        cur.close()
        return redirect(url_for("empleado.reservas_empleado"))

    try:
        documento = request.form["documento"]
        telefono = request.form["telefono"]
        hora = request.form["hora"]
        cant_personas = request.form["cant_personas"]
        tipo_evento = request.form["tipo_evento"]
        comentarios = request.form.get("comentarios", "")

        cur.execute("""
            INSERT INTO reservas (
                nombre, documento, telefono, fecha, hora,
                cant_personas, tipo_evento, comentarios, id_usuario, estado
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'Pendiente')
        """, (nombre, documento, telefono, fecha, hora,
              cant_personas, tipo_evento, comentarios, id_usuario))
        mysql.connection.commit()
        flash(f"✅ Reserva creada para {nombre} el {fecha} ({cant_personas} personas)", "success")

    except Exception as e:
        mysql.connection.rollback()
        flash(f"❌ Error al crear reserva: {str(e)}", "danger")
        print(f"Error: {e}")

    finally:
        cur.close()
    
    return redirect(url_for('empleado.reservas_empleado'))


# ===============================
# EDITAR RESERVA
# ===============================
@empleado_bp.route('/empleado/editar_reserva/<int:id_reserva>', methods=['POST'])
def editar_reserva(id_reserva):
    es_empleado, mensaje = verificar_empleado()
    if not es_empleado:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))
    
    nueva_fecha = request.form["fecha"]
    nombre = request.form["nombre"]

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Validar fecha duplicada
    cur.execute("""
        SELECT COUNT(*) AS total FROM reservas
        WHERE fecha = %s AND id_reserva != %s
    """, (nueva_fecha, id_reserva))
    count = cur.fetchone()["total"]

    if count > 0:
        flash(f"⚠️ Ya existe otra reserva para el {nueva_fecha}", "warning")
        cur.close()
        return redirect(url_for('empleado.reservas_empleado'))

    try:
        cur.execute("""
            UPDATE reservas SET
                nombre=%s, documento=%s, telefono=%s, fecha=%s, hora=%s,
                cant_personas=%s, tipo_evento=%s, comentarios=%s, id_usuario=%s
            WHERE id_reserva=%s
        """, (
            nombre, 
            request.form["documento"],
            request.form["telefono"],
            nueva_fecha,
            request.form["hora"],
            request.form["cant_personas"],
            request.form["tipo_evento"],
            request.form["comentarios"],
            request.form["id_usuario"],
            id_reserva
        ))
        
        mysql.connection.commit()
        flash(f"✅ Reserva de {nombre} actualizada correctamente", "success")
        
    except Exception as e:
        mysql.connection.rollback()
        flash(f"❌ Error al actualizar reserva: {str(e)}", "danger")
    
    cur.close()
    return redirect(url_for('empleado.reservas_empleado'))


# ===============================
# ELIMINAR RESERVA
# ===============================
@empleado_bp.route('/empleado/eliminar_reserva/<int:id_reserva>', methods=['POST'])
def eliminar_reserva(id_reserva):
    es_empleado, mensaje = verificar_empleado()
    if not es_empleado:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))
    
    try:
        cur = mysql.connection.cursor()
        
        # Obtener info antes de eliminar
        cur.execute("SELECT nombre, fecha FROM reservas WHERE id_reserva=%s", (id_reserva,))
        reserva = cur.fetchone()
        
        if reserva:
            cur.execute("DELETE FROM reservas WHERE id_reserva=%s", (id_reserva,))
            mysql.connection.commit()
            flash(f"🗑️ Reserva de {reserva['nombre']} ({reserva['fecha']}) eliminada", "info")
        else:
            flash("⚠️ Reserva no encontrada", "warning")
        
        cur.close()
        
    except Exception as e:
        flash(f"❌ Error al eliminar reserva: {str(e)}", "danger")
    
    return redirect(url_for('empleado.reservas_empleado'))


# ===============================
# CAMBIAR ESTADO RESERVA
# ===============================
@empleado_bp.route('/empleado/cambiar_estado_reserva/<int:id_reserva>', methods=['POST'])
def cambiar_estado_reserva(id_reserva):
    es_empleado, mensaje = verificar_empleado()
    if not es_empleado:
        return jsonify({"error": mensaje}), 403

    data = request.get_json()
    nuevo_estado = data.get("nuevo_estado")

    if nuevo_estado not in ["Confirmada", "Completada"]:
        return jsonify({"error": "Estado no válido"}), 400

    try:
        cur = mysql.connection.cursor()
        cur.execute("UPDATE reservas SET estado = %s WHERE id_reserva = %s", (nuevo_estado, id_reserva))
        mysql.connection.commit()
        cur.close()
        
        estado_emoji = '✅' if nuevo_estado == 'Confirmada' else '🎉'
        return jsonify({
            "success": True, 
            "message": f"{estado_emoji} Estado actualizado a {nuevo_estado}"
        }), 200
    except Exception as e:
        print(f"Error al actualizar estado: {e}")
        return jsonify({"success": False, "error": "❌ Error interno del servidor"}), 500


# ===============================
# HISTORIAL RESERVAS AGRUPADO POR MES
# ===============================
@empleado_bp.route('/empleado/historial_reservas')
def historial_reservas_em():
    es_empleado, mensaje = verificar_empleado()
    if not es_empleado:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))

    # Recibir parámetro de búsqueda
    query = request.args.get('query', '').strip()

    cur = mysql.connection.cursor()

    # Consulta base
    sql = """
        SELECT id_reserva, nombre, documento, telefono,
               fecha, hora, cant_personas, tipo_evento, id_usuario,
               estado, comentarios
        FROM reservas
        WHERE estado = 'Completada'
    """

    params = []

    # Si hay búsqueda, agregar filtros
    if query:
        sql += """
            AND (
                nombre LIKE %s OR
                telefono LIKE %s OR
                documento LIKE %s
            )
        """
        params.extend([f"%{query}%", f"%{query}%", f"%{query}%"])

    sql += " ORDER BY fecha DESC LIMIT 200"

    cur.execute(sql, params)
    historial = cur.fetchall()
    cur.close()

    # ================================
    # AGRUPAR POR MES
    # ================================
    meses_nombres = {
        '01': 'Enero', '02': 'Febrero', '03': 'Marzo', '04': 'Abril',
        '05': 'Mayo', '06': 'Junio', '07': 'Julio', '08': 'Agosto',
        '09': 'Septiembre', '10': 'Octubre', '11': 'Noviembre', '12': 'Diciembre'
    }

    historial_por_mes = {}

    for r in historial:
        fecha = str(r['fecha'])  # YYYY-MM-DD
        mes_num = fecha[5:7]     # "06"
        mes_nombre = meses_nombres.get(mes_num, "Desconocido")

        if mes_nombre not in historial_por_mes:
            historial_por_mes[mes_nombre] = []

        historial_por_mes[mes_nombre].append(r)

    return render_template(
        'historial_reservas_em.html',
        historial_por_mes=historial_por_mes,
        query=query
    )

# ===============================
# PERFIL EMPLEADO (HTML)
# ===============================
@empleado_bp.route("/empleado/perfil")
def perfil_empleado():
    if "id_usuario" not in session:
        flash("⚠️ Debes iniciar sesión primero", "danger")
        return redirect(url_for("auth.login"))

    return render_template("perfil_empleado.html")


# ===============================
# API: OBTENER DATOS DEL PERFIL (JSON)
# ===============================
@empleado_bp.route("/empleado/api/perfil", methods=["GET"])
def api_perfil_empleado():
    if "id_usuario" not in session:
        return jsonify({"error": True, "mensaje": "No logueado"}), 401

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("""
        SELECT id_usuario, nombre, apellido, telefono, direccion, correo
        FROM usuarios WHERE id_usuario = %s
    """, (session["id_usuario"],))
    empleado = cur.fetchone()
    cur.close()

    return jsonify(empleado)


# ===============================
# API: ACTUALIZAR PERFIL
# ===============================
@empleado_bp.route("/empleado/api/perfil", methods=["POST"])
def api_actualizar_perfil_empleado():
    if "id_usuario" not in session:
        return jsonify({"error": True, "mensaje": "No logueado"}), 401

    data = request.get_json()
    cur = mysql.connection.cursor()
    cur.execute("""
        UPDATE usuarios
        SET nombre=%s, apellido=%s, telefono=%s, direccion=%s, correo=%s
        WHERE id_usuario=%s
    """, (
        data["nombre"], data["apellido"], data["telefono"],
        data["direccion"], data["correo"], session["id_usuario"]
    ))
    mysql.connection.commit()
    cur.close()

    return jsonify({"error": False, "mensaje": "✅ Perfil actualizado correctamente"})


# ===============================
# API: CAMBIAR CONTRASEÑA
# ===============================
@empleado_bp.route("/empleado/api/cambiar_contrasena", methods=["POST"])
def api_cambiar_contrasena_empleado():
    if "id_usuario" not in session:
        return jsonify({"error": True, "mensaje": "No logueado"}), 401

    data = request.get_json()
    old_pass = data.get("oldPass")
    new_pass = data.get("newPass")

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT contraseña FROM usuarios WHERE id_usuario = %s", (session["id_usuario"],))
    empleado = cur.fetchone()

    if not empleado:
        cur.close()
        return jsonify({"error": True, "mensaje": "Usuario no encontrado"}), 404

    if not check_password_hash(empleado["contraseña"], old_pass):
        cur.close()
        return jsonify({"error": True, "mensaje": "❌ La contraseña actual no es correcta"}), 400

    new_hashed = generate_password_hash(new_pass)
    cur.execute("UPDATE usuarios SET contraseña = %s WHERE id_usuario = %s", (new_hashed, session["id_usuario"]))
    mysql.connection.commit()
    cur.close()

    return jsonify({"error": False, "mensaje": "✅ Contraseña actualizada con éxito"})


# ===============================
# REGISTRAR BLUEPRINT
# ===============================
def init_app(app):
    app.register_blueprint(empleado_bp)