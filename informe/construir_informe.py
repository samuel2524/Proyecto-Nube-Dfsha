"""Genera el informe autónomo y conserva una copia de los documentos reemplazados.

Uso: python informe/construir_informe.py
La portada sigue APA 7 para trabajos de estudiantes; las citas del cuerpo se
mantienen en la numeración IEEE existente, según el alcance de la edición.
"""
from documento_academico import build


if __name__ == '__main__':
    build()
