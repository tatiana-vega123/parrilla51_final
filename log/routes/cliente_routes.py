from flask import Blueprint, render_template, session, redirect, url_for, request, flash, jsonify
from __init__ import mysql
import MySQLdb.cursors
from datetime import datetime, date
from werkzeug.security import check_password_hash, generate_password_hash

cliente_bp = Blueprint('cliente', __name__)

# ==================== RESERVAR ====================
@cliente_bp.route('/cliente/reservar', methods=['GET', 'POST'])
def cliente_reservar():
    if 'rol' not in session or session['rol'] != 'cliente':
        flash("⚠️ Debes iniciar sesión como cliente", "warning")
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        try:
            nombre = request.form['nombre']
            documento = request.form['documento']
            fecha = request.form['fecha']
            hora = request.form['hora']
            cant_personas = request.form['cant_personas']
            tipo_evento = request.form['tipo_evento']
            comentarios = request.form['comentarios']
            telefono = request.form['telefono']
            id_usuario = session.get('id_usuario')

            # Validar fecha pasada
            fecha_reserva = datetime.strptime(fecha, '%Y-%m-%d').date()
            if fecha_reserva < date.today():
                flash("⚠️ No puedes reservar en fechas pasadas", "warning")
                return redirect(url_for('cliente.cliente_reservar'))

            cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
            
            # Verificar si ya tiene reserva ese día
            cur.execute("""
                SELECT COUNT(*) as total FROM reservas 
                WHERE fecha = %s AND id_usuario = %s
            """, (fecha, id_usuario))
            existe = cur.fetchone()
            
            if existe and existe['total'] > 0:
                flash("⚠️ Ya tienes una reserva para esta fecha", "warning")
                cur.close()
                return redirect(url_for('cliente.cliente_reservar'))
            
            cur.execute("""
                INSERT INTO reservas (nombre, documento, fecha, hora, cant_personas, tipo_evento, comentarios, telefono, id_usuario, estado)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'Pendiente')
            """, (nombre, documento, fecha, hora, cant_personas, tipo_evento, comentarios, telefono, id_usuario))
            mysql.connection.commit()
            cur.close()

            flash(f"✅ Reserva confirmada para {cant_personas} personas el {fecha}", "success")
            return redirect(url_for('dashboard.cliente_dashboard'))

        except Exception as e:
            mysql.connection.rollback()
            flash(f"❌ Error al crear la reserva: {str(e)}", "danger")
            print(f"Error: {e}")

    return render_template('cliente_reservar.html')


# ==================== PRODUCTOS ====================
@cliente_bp.route('/productos')
def cliente_productos():
    if 'rol' not in session or session['rol'] != 'cliente':
        flash("⚠️ Debes iniciar sesión como cliente", "warning")
        return redirect(url_for('auth.login'))

    try:
        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        # ✅ Solo productos activos/disponibles
        cur.execute("""
            SELECT 
                p.id_producto,
                p.nombre,
                p.precio,
                p.descripcion,
                p.imagen,
                p.cantidad,
                c.nombre_categoria
            FROM productos p
            LEFT JOIN categorias c ON p.cod_categoria = c.id_categoria
            WHERE p.estado = 'Disponible' AND p.cantidad > 0
        """)
        productos = cur.fetchall()
        cur.close()

        return render_template('cliente_productos.html', productos=productos)

    except Exception as e:
        print(f"Error al cargar productos: {e}")
        flash("❌ No se pudieron cargar los productos", "danger")
        return render_template('cliente_productos.html', productos=[])


# ==================== AGREGAR AL CARRITO ====================
@cliente_bp.route('/agregar_carrito/<int:id_producto>', methods=['POST', 'GET'])
def agregar_carrito(id_producto):
    try:
        cantidad = int(request.form.get('cantidad', 1))

        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cur.execute("SELECT * FROM productos WHERE id_producto = %s", (id_producto,))
        producto = cur.fetchone()
        cur.close()

        if not producto:
            flash("⚠️ Producto no encontrado", "warning")
            return redirect(url_for('cliente.cliente_productos'))

        # ✅ Validar stock disponible
        if producto['cantidad'] < cantidad:
            flash(f"⚠️ Stock insuficiente. Solo hay {producto['cantidad']} unidad(es) disponibles de {producto['nombre']}", "warning")
            return redirect(url_for('cliente.cliente_productos'))

        # ✅ Validar estado del producto
        if producto['estado'] != 'Disponible':
            flash(f"⚠️ {producto['nombre']} no está disponible actualmente", "warning")
            return redirect(url_for('cliente.cliente_productos'))

        carrito = session.get('carrito', [])
        
        # Verificar si ya existe en el carrito
        existe = False
        for item in carrito:
            if item['id_producto'] == id_producto:
                # ✅ Validar stock total (carrito + nueva cantidad)
                nueva_cantidad = item['cantidad'] + cantidad
                if nueva_cantidad > producto['cantidad']:
                    flash(f"⚠️ Stock insuficiente. Solo hay {producto['cantidad']} unidad(es) disponibles de {producto['nombre']}", "warning")
                    return redirect(url_for('cliente.cliente_productos'))
                
                item['cantidad'] = nueva_cantidad
                existe = True
                break
        
        if not existe:
            carrito.append({
                'id_producto': producto['id_producto'],
                'nombre': producto['nombre'],
                'precio': producto['precio'],
                'cantidad': cantidad
            })

        session['carrito'] = carrito
        flash(f"✅ {producto['nombre']} agregado al carrito ({cantidad} unidad/es)", "success")
        return redirect(url_for('cliente.cliente_productos'))

    except Exception as e:
        print(f"Error: {e}")
        flash("❌ Error al agregar producto al carrito", "danger")
        return redirect(url_for('cliente.cliente_productos'))


# ==================== VER CARRITO ====================
@cliente_bp.route('/cliente/carrito')
def cliente_carrito():
    if 'rol' not in session or session['rol'] != 'cliente':
        flash("⚠️ Debes iniciar sesión como cliente", "warning")
        return redirect(url_for('auth.login'))

    carrito = session.get('carrito', [])
    total = sum(item['precio'] * item['cantidad'] for item in carrito)

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("""
        SELECT p.* 
        FROM productos p
        LEFT JOIN categorias c ON p.cod_categoria = c.id_categoria
        WHERE c.nombre_categoria = 'Acompañamientos' AND p.estado = 'Disponible' AND p.cantidad > 0
    """)
    acompanamientos = cur.fetchall()
    cur.close()

    return render_template(
        'cliente_carrito.html',
        carrito=carrito,
        total=total,
        acompanamientos=acompanamientos
    )


# ==================== ELIMINAR DEL CARRITO ====================
@cliente_bp.route("/carrito/eliminar/<int:id_producto>")
def eliminar_carrito(id_producto):
    carrito = session.get("carrito", [])
    producto_eliminado = None
    
    for item in carrito:
        if item["id_producto"] == id_producto:
            producto_eliminado = item['nombre']
            break
    
    nuevo_carrito = [item for item in carrito if item["id_producto"] != id_producto]
    session["carrito"] = nuevo_carrito

    if producto_eliminado:
        flash(f"🗑️ {producto_eliminado} eliminado del carrito", "info")
    else:
        flash("⚠️ Producto no encontrado en el carrito", "warning")
    
    return redirect(url_for("cliente.cliente_carrito"))


# ==================== CONFIRMAR PEDIDO ====================
@cliente_bp.route("/pedido/confirmar", methods=["POST"])
def hacer_pedido():
    carrito = session.get("carrito", [])
    
    if not carrito:
        flash("⚠️ Tu carrito está vacío", "warning")
        return redirect(url_for("cliente.cliente_productos"))

    # Validar acompañamientos
    acompanamientos_ids = request.form.getlist("acompanamientos")
    if len(acompanamientos_ids) != 2:
        flash("⚠️ Debes seleccionar exactamente 2 acompañamientos", "warning")
        return redirect(url_for("cliente.cliente_carrito"))

    tipo_entrega = request.form.get("tipo_entrega", "restaurante")
    
    # Validar domicilio
    if tipo_entrega == "domicilio":
        direccion = request.form.get("direccion", "").strip()
        telefono = request.form.get("telefono_envio", "").strip()
        
        if not direccion or not telefono:
            flash("⚠️ Completa la dirección y teléfono para domicilio", "warning")
            return redirect(url_for("cliente.cliente_carrito"))
    else:
        direccion = None
        telefono = None

    total = sum(item["precio"] * item["cantidad"] for item in carrito)
    metodo_pago = request.form.get("metodo_pago", "efectivo")
    id_usuario = session.get("id_usuario")

    try:
        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

        # ✅ VALIDAR STOCK ANTES DE CONFIRMAR
        stock_insuficiente = []
        
        # Validar productos del carrito
        for item in carrito:
            cur.execute("SELECT nombre, cantidad, estado FROM productos WHERE id_producto = %s", (item["id_producto"],))
            producto = cur.fetchone()
            
            if not producto:
                stock_insuficiente.append(f"{item['nombre']} (no encontrado)")
            elif producto['estado'] != 'Disponible':
                stock_insuficiente.append(f"{item['nombre']} (no disponible)")
            elif producto["cantidad"] < item["cantidad"]:
                stock_insuficiente.append(f"{item['nombre']} (solo quedan {producto['cantidad']} unidades)")
        
        # Validar acompañamientos
        for id_acomp in acompanamientos_ids:
            cur.execute("SELECT nombre, cantidad, estado FROM productos WHERE id_producto = %s", (int(id_acomp),))
            acomp = cur.fetchone()
            
            if not acomp:
                stock_insuficiente.append(f"Acompañamiento ID {id_acomp} (no encontrado)")
            elif acomp['estado'] != 'Disponible':
                stock_insuficiente.append(f"{acomp['nombre']} (no disponible)")
            elif acomp["cantidad"] < 1:
                stock_insuficiente.append(f"{acomp['nombre']} (sin stock)")
        
        if stock_insuficiente:
            flash(f"❌ Stock insuficiente: {', '.join(stock_insuficiente)}. Intenta de nuevo más tarde", "danger")
            cur.close()
            return redirect(url_for("cliente.cliente_carrito"))

        # ✅ CREAR PEDIDO
        cur.execute("""
            INSERT INTO pedidos (
                cod_usuario, fecha, hora, total, estado,
                tipo_entrega, metodo_pago, direccion, telefono
            ) VALUES (
                %s, CURDATE(), CURTIME(), %s, 'pendiente',
                %s, %s, %s, %s
            )
        """, (id_usuario, total, tipo_entrega, metodo_pago, direccion, telefono))

        id_pedido = cur.lastrowid

        # ✅ INSERTAR PRODUCTOS Y REDUCIR STOCK
        for item in carrito:
            cur.execute("""
                INSERT INTO detalle_pedido (
                    cod_pedido, cod_producto, cantidad, precio_unitario
                ) VALUES (%s, %s, %s, %s)
            """, (id_pedido, item["id_producto"], item["cantidad"], item["precio"]))
            
            # ✅ REDUCIR STOCK
            cur.execute("""
                UPDATE productos 
                SET cantidad = cantidad - %s 
                WHERE id_producto = %s
            """, (item["cantidad"], item["id_producto"]))

        # ✅ INSERTAR ACOMPAÑAMIENTOS Y REDUCIR STOCK
        for id_acomp in acompanamientos_ids:
            cur.execute("""
                INSERT INTO detalle_pedido (
                    cod_pedido, cod_producto, cantidad, precio_unitario
                ) VALUES (%s, %s, 1, 0)
            """, (id_pedido, int(id_acomp)))
            
            # ✅ REDUCIR STOCK DE ACOMPAÑAMIENTO
            cur.execute("""
                UPDATE productos 
                SET cantidad = cantidad - 1 
                WHERE id_producto = %s
            """, (int(id_acomp),))

        mysql.connection.commit()
        cur.close()

        session.pop("carrito", None)
        
        tipo_texto = "domicilio" if tipo_entrega == "domicilio" else "mesa"
        flash(f"✅ Pedido #{id_pedido} confirmado para {tipo_texto}. Total: ${total:,.0f}", "success")
        return redirect(url_for("dashboard.cliente_dashboard"))

    except Exception as e:
        mysql.connection.rollback()
        flash(f"❌ Error al procesar el pedido: {str(e)}", "danger")
        print(f"Error: {e}")
        return redirect(url_for("cliente.cliente_carrito"))


# ==================== VER RESERVAS ====================
@cliente_bp.route('/cliente/ver_reservas')
def cliente_ver_reservas():
    if 'rol' not in session or session['rol'] != 'cliente':
        flash("⚠️ Debes iniciar sesión como cliente", "warning")
        return redirect(url_for('auth.login'))

    id_usuario = session.get('id_usuario')

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("""
        SELECT id_reserva, nombre, fecha, hora, cant_personas, tipo_evento, estado, comentarios
        FROM reservas
        WHERE id_usuario = %s
        ORDER BY fecha DESC
    """, (id_usuario,))
    reservas = cur.fetchall()
    cur.close()

    return render_template('cliente_ver_reservas.html', reservas=reservas)


# ==================== MIS PEDIDOS ====================
@cliente_bp.route('/mis_pedidos')
def cliente_mis_pedidos():
    if 'rol' not in session or session['rol'] != 'cliente':
        flash("⚠️ Debes iniciar sesión como cliente", "warning")
        return redirect(url_for('auth.login'))

    id_usuario = session.get('id_usuario')
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    cur.execute("""
        SELECT 
            pe.id_pedido,
            pe.tipo_entrega,
            pe.fecha,
            pe.hora,
            pe.metodo_pago,
            pe.total,
            pe.estado,
            u.nombre AS nombre_usuario
        FROM pedidos pe
        LEFT JOIN usuarios u ON pe.cod_usuario = u.id_usuario
        WHERE pe.cod_usuario = %s
        ORDER BY pe.id_pedido DESC
    """, (id_usuario,))
    pedidos = cur.fetchall()

    pedidos_final = []
    for pedido in pedidos:
        cur.execute("""
            SELECT 
                dp.cod_producto,
                p.nombre AS nombre_producto,
                dp.cantidad,
                dp.precio_unitario
            FROM detalle_pedido dp
            LEFT JOIN productos p ON dp.cod_producto = p.id_producto
            WHERE dp.cod_pedido = %s
        """, (pedido["id_pedido"],))
        productos = cur.fetchall()

        pedidos_final.append({
            "id_pedido": pedido["id_pedido"],
            "fecha": pedido["fecha"],
            "hora": pedido["hora"],
            "total": pedido["total"],
            "estado": pedido["estado"],
            "tipo_entrega": pedido["tipo_entrega"],
            "metodo_pago": pedido["metodo_pago"],
            "nombre_usuario": pedido.get("nombre_usuario"),
            "productos": productos
        })

    cur.close()
    return render_template('mis_pedidos.html', pedidos=pedidos_final)


# ==================== API: PERFIL ====================
@cliente_bp.route('/cliente/api/perfil', methods=['GET'])
def api_get_perfil():
    if 'id_usuario' not in session:
        return jsonify({"error": "No logueado"}), 401

    user_id = session['id_usuario']

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("""
        SELECT nombre, apellido, telefono, direccion, correo
        FROM usuarios
        WHERE id_usuario = %s
    """, (user_id,))
    data = cur.fetchone()
    cur.close()

    if not data:
        return jsonify({"error": "Usuario no encontrado"}), 404

    return jsonify(data)


@cliente_bp.route('/cliente/api/perfil', methods=['POST'])
def api_guardar_perfil():
    if 'id_usuario' not in session:
        return jsonify({"mensaje": "No logueado"}), 401

    data = request.json
    user_id = session['id_usuario']

    cur = mysql.connection.cursor()
    cur.execute("""
        UPDATE usuarios
        SET nombre=%s, apellido=%s, telefono=%s, direccion=%s, correo=%s
        WHERE id_usuario=%s
    """, (
        data['nombre'], data['apellido'], data['telefono'],
        data['direccion'], data['correo'], user_id
    ))

    mysql.connection.commit()
    cur.close()

    flash("✅ Perfil actualizado correctamente", "success")
    return jsonify({"mensaje": "Datos actualizados correctamente"})


@cliente_bp.route('/cliente/api/cambiar_contrasena', methods=['POST'])
def api_cambiar_contrasena():
    if 'id_usuario' not in session:
        return jsonify({"mensaje": "No logueado"}), 401

    data = request.json
    user_id = session['id_usuario']

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT contraseña FROM usuarios WHERE id_usuario=%s", (user_id,))
    user = cur.fetchone()

    if not user:
        return jsonify({"mensaje": "Usuario no encontrado"}), 404

    if not check_password_hash(user["contraseña"], data["oldPass"]):
        return jsonify({"mensaje": "❌ La contraseña actual es incorrecta"}), 400

    nueva_hash = generate_password_hash(data["newPass"])

    cur.execute("""
        UPDATE usuarios 
        SET contraseña=%s
        WHERE id_usuario=%s
    """, (nueva_hash, user_id))

    mysql.connection.commit()
    cur.close()

    return jsonify({"mensaje": "✅ Contraseña cambiada correctamente"})


def init_app(app):
    app.register_blueprint(cliente_bp)