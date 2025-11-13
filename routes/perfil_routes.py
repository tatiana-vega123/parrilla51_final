# routes/perfil_routes.py

from flask import Blueprint, jsonify, session, request
from werkzeug.security import check_password_hash, generate_password_hash
from __init__ import mysql

perfil_bp = Blueprint("perfil_bp", __name__)  # ✅ nombre correcto del blueprint


# ✅ Obtener datos del usuario
@perfil_bp.route('/perfil/datos', methods=['GET'])
def obtener_datos():
    user_id = session.get("id_usuario")

    if not user_id:
        return jsonify({"error": "Debes iniciar sesión"}), 401
    
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT nombre, apellido, telefono, direccion, correo
        FROM usuario
        WHERE id = %s
    """, (user_id,))
    data = cur.fetchone()
    cur.close()

    if not data:
        return jsonify({"error": "Usuario no encontrado"}), 404

    return jsonify({
        "nombre": data["nombre"],
        "apellido": data["apellido"],
        "telefono": data["telefono"],
        "direccion": data["direccion"],
        "correo": data["correo"]
    })


# ✅ Actualizar perfil
@perfil_bp.route('/perfil/editar', methods=['POST'])
def editar_perfil():
    user_id = session.get("id_usuario")

    if not user_id:
        return jsonify({"error": "Debes iniciar sesión"}), 401
    
    data = request.get_json()

    cur = mysql.connection.cursor()
    cur.execute("""
        UPDATE usuario
        SET nombre=%s, apellido=%s, telefono=%s, direccion=%s, correo=%s
        WHERE id = %s
    """, (
        data["nombre"], data["apellido"], data["telefono"],
        data["direccion"], data["correo"], user_id
    ))
    mysql.connection.commit()
    cur.close()

    return jsonify({"mensaje": "✅ Perfil actualizado"})


# ✅ Cambiar contraseña
@perfil_bp.route('/perfil/cambiar_contrasena', methods=['POST'])
def cambiar_contrasena():
    user_id = session.get("id_usuario")

    if not user_id:
        return jsonify({"error": "Debes iniciar sesión"}), 401

    data = request.get_json()
    old_pass = data.get("oldPass")
    new_pass = data.get("newPass")

    cur = mysql.connection.cursor()
    cur.execute("SELECT clave FROM usuario WHERE id=%s", (user_id,))
    row = cur.fetchone()

    if not row:
        return jsonify({"error": "Usuario no encontrado"}), 404

    if not check_password_hash(row["clave"], old_pass):
        return jsonify({"error": "❌ Contraseña actual incorrecta"}), 400

    nueva = generate_password_hash(new_pass)
    cur.execute("UPDATE usuario SET clave=%s WHERE id=%s", (nueva, user_id))
    mysql.connection.commit()
    cur.close()

    return jsonify({"mensaje": "✅ Contraseña cambiada"})
