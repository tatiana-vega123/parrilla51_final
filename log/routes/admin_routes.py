from flask import Blueprint, render_template, session, redirect, url_for, request, flash, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from __init__ import mysql
import MySQLdb.cursors

admin_bp = Blueprint('admin', __name__)

# ===============================
# VERIFICACIÓN DE ADMINISTRADOR
# ===============================
def verificar_admin():
    """Función helper para verificar si el usuario es administrador"""
    if 'logueado' not in session:
        return False, '⚠️ Debes iniciar sesión primero'
    
    if session.get('rol') != 'administrador':
        return False, f'❌ Acceso denegado. Tu rol actual es: {session.get("rol")}'
    
    return True, None

# ===============================
# DASHBOARD
# ===============================
@admin_bp.route('/admin/dashboard')
def admin_dashboard():
    es_admin, mensaje = verificar_admin()
    if not es_admin:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))
    
    # ✅ Obtener alertas de stock bajo
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("""
        SELECT * FROM alertas 
        WHERE tipo IN ('stock', 'producto')
        ORDER BY fecha DESC 
        LIMIT 10
    """)
    alertas = cur.fetchall()
    
    # ✅ Contar productos con stock bajo
    cur.execute("""
        SELECT COUNT(*) as total FROM productos 
        WHERE cantidad < 5 AND cantidad > 0 AND estado = 'Disponible'
    """)
    stock_bajo = cur.fetchone()['total']
    
    # ✅ Contar productos sin stock
    cur.execute("""
        SELECT COUNT(*) as total FROM productos 
        WHERE cantidad = 0 AND estado = 'Disponible'
    """)
    sin_stock = cur.fetchone()['total']
    
    cur.close()
    
    return render_template('admin2.html', 
                         alertas=alertas,
                         stock_bajo=stock_bajo,
                         sin_stock=sin_stock)

# ===============================
# API: PERFIL ADMINISTRADOR
# ===============================
@admin_bp.route("/admin/api/perfil", methods=["GET"])
def api_perfil_admin():
    if "id_usuario" not in session:
        return jsonify({"error": True, "mensaje": "No logueado"}), 401

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("""
        SELECT id_usuario, nombre, apellido, telefono, direccion, correo
        FROM usuarios WHERE id_usuario = %s
    """, (session["id_usuario"],))
    admin = cur.fetchone()
    cur.close()

    return jsonify(admin)

@admin_bp.route("/admin/api/perfil", methods=["POST"])
def api_actualizar_perfil_admin():
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

@admin_bp.route("/admin/api/cambiar_contrasena", methods=["POST"])
def api_cambiar_contrasena_admin():
    if "id_usuario" not in session:
        return jsonify({"error": True, "mensaje": "No logueado"}), 401

    data = request.get_json()
    old_pass = data.get("oldPass")
    new_pass = data.get("newPass")

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT contraseña FROM usuarios WHERE id_usuario = %s", (session["id_usuario"],))
    admin = cur.fetchone()

    if not admin:
        cur.close()
        return jsonify({"error": True, "mensaje": "Usuario no encontrado"}), 404

    if not check_password_hash(admin["contraseña"], old_pass):
        cur.close()
        return jsonify({"error": True, "mensaje": "❌ La contraseña actual no es correcta"}), 400

    new_hashed = generate_password_hash(new_pass)
    cur.execute("UPDATE usuarios SET contraseña = %s WHERE id_usuario = %s", (new_hashed, session["id_usuario"]))
    mysql.connection.commit()
    cur.close()

    return jsonify({"error": False, "mensaje": "✅ Contraseña actualizada correctamente"})

# ===============================
# PRODUCTOS
# ===============================
@admin_bp.route('/admin/productos', methods=['GET', 'POST'])
def admin_productos():
    es_admin, mensaje = verificar_admin()
    if not es_admin:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # ✅ Mostrar TODOS los productos (disponibles y no disponibles)
    cur.execute("""
        SELECT p.id_producto, p.nombre, p.cantidad, p.descripcion, p.precio, 
               p.imagen, p.estado, c.nombre_categoria, p.cod_categoria
        FROM productos p
        LEFT JOIN categorias c ON p.cod_categoria = c.id_categoria
        ORDER BY p.estado DESC, p.cantidad ASC
    """)
    productos = cur.fetchall()
    
    # ✅ Obtener alertas de stock
    cur.execute("""
        SELECT * FROM alertas 
        WHERE tipo = 'stock'
        ORDER BY fecha DESC 
        LIMIT 5
    """)
    alertas_stock = cur.fetchall()
    
    cur.close()
    
    return render_template('admin_productos.html', 
                         productos=productos,
                         alertas_stock=alertas_stock)


@admin_bp.route('/admin/productos/agregar', methods=['GET', 'POST'])
def agregar_producto():
    es_admin, mensaje = verificar_admin()
    if not es_admin:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        nombre = request.form['nombre']
        cantidad = request.form['cantidad']
        precio = request.form['precio']

        try:
            cur = mysql.connection.cursor()
            cur.execute("""
                INSERT INTO productos (nombre, cantidad, descripcion, precio, cod_categoria, imagen, estado)
                VALUES (%s, %s, %s, %s, %s, %s, 'Disponible')
            """, (
                nombre,
                cantidad,
                request.form['descripcion'],
                precio,
                request.form['cod_categoria'],
                request.form.get('imagen', '')
            ))
            mysql.connection.commit()
            cur.close()

            flash(f"✅ Producto '{nombre}' agregado correctamente", "success")
            return redirect(url_for('admin.admin_productos'))
            
        except Exception as e:
            flash(f"❌ Error al agregar producto: {str(e)}", "danger")

    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM categorias")
    categorias = cur.fetchall()
    cur.close()
    
    return render_template('editar_producto.html', producto=None, categorias=categorias)


@admin_bp.route('/admin/productos/editar/<int:id_producto>', methods=['GET', 'POST'])
def editar_producto(id_producto):
    es_admin, mensaje = verificar_admin()
    if not es_admin:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT * FROM productos WHERE id_producto = %s", (id_producto,))
    producto = cur.fetchone()

    if request.method == 'POST':
        nombre = request.form['nombre']
        
        try:
            cur.execute("""
                UPDATE productos SET nombre=%s, cantidad=%s, descripcion=%s, precio=%s,
                                    cod_categoria=%s, imagen=%s
                WHERE id_producto=%s
            """, (
                nombre,
                request.form['cantidad'],
                request.form['descripcion'],
                request.form['precio'],
                request.form['cod_categoria'],
                request.form.get('imagen', ''),
                id_producto
            ))
            mysql.connection.commit()
            flash(f"✅ Producto '{nombre}' actualizado correctamente", "success")
            return redirect(url_for('admin.admin_productos'))
            
        except Exception as e:
            flash(f"❌ Error al actualizar producto: {str(e)}", "danger")

    cur.execute("SELECT * FROM categorias")
    categorias = cur.fetchall()
    cur.close()

    return render_template('editar_producto.html', producto=producto, categorias=categorias)


# ✅ CAMBIAR A ACTIVAR/DESACTIVAR EN LUGAR DE ELIMINAR
@admin_bp.route('/admin/productos/toggle/<int:id_producto>', methods=['POST', 'GET'])
def toggle_producto(id_producto):
    es_admin, mensaje = verificar_admin()
    if not es_admin:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))

    try:
        cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        
        # Obtener estado actual
        cur.execute("SELECT nombre, estado FROM productos WHERE id_producto = %s", (id_producto,))
        producto = cur.fetchone()
        
        if not producto:
            flash("⚠️ Producto no encontrado", "warning")
        else:
            # Cambiar estado
            nuevo_estado = 'No disponible' if producto['estado'] == 'Disponible' else 'Disponible'
            cur.execute("UPDATE productos SET estado = %s WHERE id_producto = %s", 
                       (nuevo_estado, id_producto))
            mysql.connection.commit()
            
            emoji = '✅' if nuevo_estado == 'Disponible' else '🔴'
            accion = 'activado' if nuevo_estado == 'Disponible' else 'desactivado'
            flash(f"{emoji} Producto '{producto['nombre']}' {accion}", "success")
        
        cur.close()
        
    except Exception as e:
        flash(f"❌ Error al cambiar estado del producto: {str(e)}", "danger")

    return redirect(url_for('admin.admin_productos'))


# Mantener eliminar por si acaso (opcional)
@admin_bp.route('/admin/productos/eliminar/<int:id_producto>', methods=['POST', 'GET'])
def eliminar_producto(id_producto):
    es_admin, mensaje = verificar_admin()
    if not es_admin:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))

    try:
        cur = mysql.connection.cursor()
        
        cur.execute("SELECT nombre FROM productos WHERE id_producto = %s", (id_producto,))
        producto = cur.fetchone()
        
        if not producto:
            flash("⚠️ Producto no encontrado", "warning")
        else:
            cur.execute("DELETE FROM productos WHERE id_producto = %s", (id_producto,))
            mysql.connection.commit()
            flash(f"🗑️ Producto '{producto['nombre']}' eliminado permanentemente", "info")
        
        cur.close()
        
    except Exception as e:
        flash(f"❌ Error al eliminar producto: {str(e)}", "danger")

    return redirect(url_for('admin.admin_productos'))

# ===============================
# RESERVAS
# ===============================
@admin_bp.route('/admin/reservas')
def admin_reservas():
    es_admin, mensaje = verificar_admin()
    if not es_admin:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))

    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM reservas ORDER BY fecha DESC")
    reservas = cur.fetchall()
    cur.close()
    return render_template('admin_reservas.html', reservas=reservas)

# ===============================
# PEDIDOS
# ===============================
@admin_bp.route('/admin/pedidos')
def admin_pedidos():
    es_admin, mensaje = verificar_admin()
    if not es_admin:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT p.id_pedido, u.nombre, u.apellido, p.fecha, p.hora, 
               p.total, p.estado, p.tipo_entrega
        FROM pedidos p
        LEFT JOIN usuarios u ON p.cod_usuario = u.id_usuario
        ORDER BY p.fecha DESC, p.hora DESC
    """)
    pedidos = cur.fetchall()
    cur.close()

    return render_template('admin_pedidos.html', pedidos=pedidos)


@admin_bp.route('/admin/pedidos/estado/<int:id_pedido>/<string:nuevo_estado>')
def cambiar_estado_pedido(id_pedido, nuevo_estado):
    es_admin, mensaje = verificar_admin()
    if not es_admin:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))

    try:
        cur = mysql.connection.cursor()
        cur.execute("UPDATE pedidos SET estado=%s WHERE id_pedido=%s", (nuevo_estado, id_pedido))
        mysql.connection.commit()
        cur.close()

        estado_texto = {
            'entregado': '✅ entregado',
            'cancelado': '❌ cancelado',
            'pendiente': '⏳ pendiente'
        }.get(nuevo_estado, nuevo_estado)

        flash(f"Estado del pedido #{id_pedido} cambiado a {estado_texto}", "success")
    except Exception as e:
        flash(f"❌ Error al cambiar estado: {str(e)}", "danger")
    
    return redirect(url_for('admin.admin_pedidos'))

# ===============================
# INVENTARIO (PRODUCTOS + INSUMOS + MESAS)
# ===============================
@admin_bp.route('/admin/inventario')
def admin_inventario():
    es_admin, mensaje = verificar_admin()
    if not es_admin:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))
    
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # ✅ Productos con alertas de stock
    cur.execute("""
        SELECT p.id_producto, p.nombre, p.cantidad, p.descripcion, p.precio, 
               p.imagen, p.estado, c.nombre_categoria, p.cod_categoria
        FROM productos p
        LEFT JOIN categorias c ON p.cod_categoria = c.id_categoria
        ORDER BY p.cantidad ASC
    """)
    productos = cur.fetchall()

    cur.execute("""
        SELECT i.id_insumo, i.nombre, i.cantidad, i.precio, i.fecha_vencimiento, i.lote,
               s.nombre_subcategoria, i.subcategoria_id
        FROM insumos i
        LEFT JOIN subcategorias_insumos s ON i.subcategoria_id = s.id_subcategoria
    """)
    insumos = cur.fetchall()

    cur.execute("SELECT * FROM mesas")
    mesas = cur.fetchall()
    
    # ✅ Alertas de stock
    cur.execute("""
        SELECT * FROM alertas 
        WHERE tipo IN ('stock', 'producto')
        ORDER BY fecha DESC 
        LIMIT 10
    """)
    alertas = cur.fetchall()
    
    cur.close()

    return render_template('inventario.html',
                           productos=productos,
                           insumos=insumos,
                           mesas=mesas,
                           alertas=alertas)

# ===============================
# INSUMOS
# ===============================
@admin_bp.route('/admin/insumos/agregar', methods=['GET', 'POST'])
def agregar_insumo():
    es_admin, mensaje = verificar_admin()
    if not es_admin:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        nombre = request.form['nombre']
        cantidad = request.form['cantidad']
        precio = request.form['precio']
        fecha_vencimiento = request.form.get('fecha_vencimiento') or None
        lote = request.form.get('lote') or None
        subcategoria_id = request.form['subcategoria_id']

        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO insumos (nombre, cantidad, precio, fecha_vencimiento, lote, subcategoria_id)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (nombre, cantidad, precio, fecha_vencimiento, lote, subcategoria_id))
        mysql.connection.commit()
        cur.close()

        flash(f"✅ Insumo '{nombre}' agregado correctamente", "success")
        return redirect(url_for('admin.admin_inventario'))

    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM subcategorias_insumos")
    subcategorias = cur.fetchall()
    cur.close()

    return render_template('editar_insumo.html', insumo=None, subcategorias=subcategorias)


@admin_bp.route('/admin/insumos/editar/<int:id_insumo>', methods=['GET', 'POST'])
def editar_insumo(id_insumo):
    es_admin, mensaje = verificar_admin()
    if not es_admin:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))

    cur = mysql.connection.cursor()

    if request.method == 'POST':
        nombre = request.form['nombre']
        cantidad = request.form['cantidad']
        precio = request.form['precio']
        fecha_vencimiento = request.form.get('fecha_vencimiento') or None
        lote = request.form.get('lote') or None
        subcategoria_id = request.form['subcategoria_id']

        cur.execute("""
            UPDATE insumos SET nombre=%s, cantidad=%s, precio=%s, 
                   fecha_vencimiento=%s, lote=%s, subcategoria_id=%s
            WHERE id_insumo=%s
        """, (nombre, cantidad, precio, fecha_vencimiento, lote, subcategoria_id, id_insumo))
        mysql.connection.commit()
        cur.close()

        flash(f"✅ Insumo '{nombre}' actualizado correctamente", "success")
        return redirect(url_for('admin.admin_inventario'))

    cur.execute("SELECT * FROM insumos WHERE id_insumo=%s", (id_insumo,))
    insumo = cur.fetchone()

    if insumo:
        if insumo['fecha_vencimiento']:
            insumo['fecha_vencimiento'] = str(insumo['fecha_vencimiento'])
        if insumo['lote']:
            insumo['lote'] = str(insumo['lote'])

    cur.execute("SELECT * FROM subcategorias_insumos")
    subcategorias = cur.fetchall()
    cur.close()

    return render_template('editar_insumo.html', insumo=insumo, subcategorias=subcategorias)


@admin_bp.route('/admin/insumos/eliminar/<int:id_insumo>', methods=['POST', 'GET'])
def eliminar_insumo(id_insumo):
    es_admin, mensaje = verificar_admin()
    if not es_admin:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))

    try:
        cur = mysql.connection.cursor()
        
        cur.execute("SELECT nombre FROM insumos WHERE id_insumo=%s", (id_insumo,))
        insumo = cur.fetchone()
        
        if insumo:
            cur.execute("DELETE FROM insumos WHERE id_insumo=%s", (id_insumo,))
            mysql.connection.commit()
            flash(f"🗑️ Insumo '{insumo['nombre']}' eliminado correctamente", "info")
        else:
            flash("⚠️ Insumo no encontrado", "warning")
        
        cur.close()
    except Exception as e:
        flash(f"❌ Error al eliminar insumo: {str(e)}", "danger")

    return redirect(url_for('admin.admin_inventario'))

# ===============================
# MESAS
# ===============================
@admin_bp.route('/admin/mesas/agregar', methods=['GET', 'POST'])
def agregar_mesa():
    es_admin, mensaje = verificar_admin()
    if not es_admin:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        numero_mesa = request.form['numero_mesa']
        capacidad = request.form['capacidad']

        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO mesas (numero_mesa, capacidad, estado)
            VALUES (%s, %s, 'Disponible')
        """, (numero_mesa, capacidad))
        mysql.connection.commit()
        cur.close()

        flash(f"✅ Mesa #{numero_mesa} agregada correctamente", "success")
        return redirect(url_for('admin.admin_inventario'))

    return render_template('editar_mesa.html', mesa=None)


@admin_bp.route('/admin/mesas/estado/<int:id_mesa>')
def cambiar_estado_mesa(id_mesa):
    es_admin, mensaje = verificar_admin()
    if not es_admin:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))

    cur = mysql.connection.cursor()
    cur.execute("SELECT estado FROM mesas WHERE id_mesa=%s", (id_mesa,))
    mesa = cur.fetchone()

    nuevo_estado = 'Disponible' if mesa['estado'] == 'Ocupada' else 'Ocupada'
    cur.execute("UPDATE mesas SET estado=%s WHERE id_mesa=%s", (nuevo_estado, id_mesa))
    mysql.connection.commit()
    cur.close()

    emoji = '✅' if nuevo_estado == 'Disponible' else '🔴'
    flash(f"{emoji} Estado de la mesa cambiado a: {nuevo_estado}", "success")
    return redirect(url_for('admin.admin_inventario'))


@admin_bp.route('/admin/mesas/eliminar/<int:id_mesa>', methods=['POST', 'GET'])
def eliminar_mesa(id_mesa):
    es_admin, mensaje = verificar_admin()
    if not es_admin:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))

    try:
        cur = mysql.connection.cursor()
        
        cur.execute("SELECT numero_mesa FROM mesas WHERE id_mesa=%s", (id_mesa,))
        mesa = cur.fetchone()
        
        if mesa:
            cur.execute("DELETE FROM mesas WHERE id_mesa=%s", (id_mesa,))
            mysql.connection.commit()
            flash(f"🗑️ Mesa #{mesa['numero_mesa']} eliminada correctamente", "info")
        else:
            flash("⚠️ Mesa no encontrada", "warning")
        
        cur.close()
    except Exception as e:
        flash(f"❌ Error al eliminar mesa: {str(e)}", "danger")

    return redirect(url_for('admin.admin_inventario'))

# ===============================
# USUARIOS
# ===============================
@admin_bp.route('/admin/usuarios')
def admin_usuarios():
    es_admin, mensaje = verificar_admin()
    if not es_admin:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))

    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM usuarios")
    usuarios = cur.fetchall()
    cur.close()

    return render_template('asignarol.html', usuarios=usuarios)


@admin_bp.route('/admin/usuarios/estado/<int:id_usuario>/<string:nuevo_estado>')
def admin_cambiar_estado_usuario(id_usuario, nuevo_estado):
    es_admin, mensaje = verificar_admin()
    if not es_admin:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))

    try:
        cur = mysql.connection.cursor()
        
        cur.execute("SELECT nombre, apellido FROM usuarios WHERE id_usuario = %s", (id_usuario,))
        usuario = cur.fetchone()
        
        if usuario:
            cur.execute("UPDATE usuarios SET estado = %s WHERE id_usuario = %s", 
                       (nuevo_estado, id_usuario))
            mysql.connection.commit()
            
            estado_texto = "activado" if nuevo_estado == "activo" else "desactivado"
            flash(f"✅ Usuario {usuario['nombre']} {usuario['apellido']} {estado_texto}", "success")
        else:
            flash("⚠️ Usuario no encontrado", "warning")
        
        cur.close()
        
    except Exception as e:
        flash(f"❌ Error al cambiar estado: {str(e)}", "danger")

    return redirect(url_for('admin.admin_usuarios'))


@admin_bp.route('/admin/usuarios/rol/<int:id_usuario>/<string:nuevo_rol>')
def admin_cambiar_rol_usuario(id_usuario, nuevo_rol):
    es_admin, mensaje = verificar_admin()
    if not es_admin:
        flash(mensaje, 'danger')
        return redirect(url_for('auth.login'))

    try:
        cur = mysql.connection.cursor()
        
        cur.execute("SELECT nombre, apellido FROM usuarios WHERE id_usuario = %s", (id_usuario,))
        usuario = cur.fetchone()
        
        if usuario:
            cur.execute("UPDATE usuarios SET rol = %s WHERE id_usuario = %s", 
                       (nuevo_rol, id_usuario))
            mysql.connection.commit()
            flash(f"✅ {usuario['nombre']} {usuario['apellido']} ahora es {nuevo_rol}", "success")
        else:
            flash("⚠️ Usuario no encontrado", "warning")
        
        cur.close()
        
    except Exception as e:
        flash(f"❌ Error al cambiar rol: {str(e)}", "danger")

    return redirect(url_for('admin.admin_usuarios'))


def init_app(app):
    app.register_blueprint(admin_bp)