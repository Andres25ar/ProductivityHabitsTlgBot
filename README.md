<h1 align="center">ProductivityHabitsTlgBot</h1>

<p align="center">
A bot for managing smart habits and personal productivity.
</p>

<p align="center">
  <img src="assets/Gemini_Generated_Image_pvre4pvre4pvre4p.png" alt="An image of a futuristic robot with binary code representing the Focus Helper Bot project.">
</p>

---

### ➤ Table of Contents

- [Overview](#-overview)
- [Key Features & Functionalities](#-key-features--functionalities)
- [Potentialities](#-potentialities)
- [Technologies Used](#-technologies-used)
- [ProductivityHabitsTlgBot (Español)](#productivityhabitstlgbot-español)

---

<h2 align="center">🚀 Overview</h2>

**ProductivityHabitsTlgBot** is a Telegram bot designed to empower users in establishing **smart habits** and boosting their **personal productivity**. By offering intuitive task management and customizable reminders, it aims to be your digital companion in achieving your daily goals and long-term aspirations. Built with **Python**, **PostgreSQL**, and **APScheduler**, this bot provides a robust and reliable solution for personal organization.

---

<h2 align="center">✨ Key Features & Functionalities</h2>

- **Intuitive User Onboarding**:
    - **User Registration**: Seamlessly registers new users upon first interaction.
    - **Interactive Timezone Configuration**: Guides users through a paginated, multi-step menu (Continent -> Country -> City) to set their timezone, ensuring reminders are always punctual and locally relevant.

- **Dynamic Task & Habit Management**:
    - **Create Tasks**: Quickly add new tasks with descriptions and due dates. Frequency (one-time, daily, weekly, etc.) is selected via an interactive button menu to minimize errors.
    - **Manage Habits**: Users can subscribe to a list of predefined habits to receive periodic reminders.
    - **List & Modify**: View all pending tasks, and mark one-time tasks as complete or delete any task.

- **Smart, Timezone-Aware Reminders**:
    - Leverages **APScheduler** to provide timely notifications for all scheduled tasks and habits.
    - All reminders are fully adapted to each user's configured timezone.
    - Habit notifications can be scheduled for multiple times per day.

- **Database Persistence**: Utilizes **PostgreSQL** to ensure all user data, tasks, and habit subscriptions are securely stored and persist across bot restarts.

- **Modular & Scalable Architecture**: Designed with a clear separation of concerns (handlers, database interactions, utilities) to facilitate future expansions and maintenance.

---

<h2 align="center">💡 Potentialities</h2>

**ProductivityHabitsTlgBot** is more than just a task manager; it's a foundation for a powerful personal assistant. Its potential can be expanded to include:

- **Enhanced User Interaction**:
    - **Natural Language for Dates**: Implement `dateparser` to allow users to set task deadlines with phrases like "tomorrow at 10am" or "next Friday".
    - **Interactive Calendar**: Add a calendar keyboard as an alternative for visual date selection.
    - **Granular Notifications**: Allow users to unsubscribe from individual habit reminders via an inline button.

- **Advanced Habit & Task Features**:
    - **Habit Tracking & Analytics**: Deeper integration of habit tracking with progress visualization and analytical reports (e.g., streaks, completion rates).
    - **Custom Habits**: Allow users to create their own custom habits instead of only subscribing to predefined ones.
    - **Goal Setting**: Features to define and track larger goals broken down into smaller, actionable tasks.

- **Integrations and AI**:
    - **Integration with External Services**: Connect with calendars (Google Calendar, Outlook) or note-taking apps.
    - **AI-Powered Suggestions**: Proactive suggestions for tasks or scheduling optimization based on user behavior.

- **Community & Gamification**:
    - **Team Collaboration**: Extend functionality for small team task management and shared habits.
    - **Gamification**: Introduce points, badges, or leaderboards to make productivity more engaging.

---

<h2 align="center">🛠️ Technologies Used</h2>

- **Python**: The core programming language.
- **python-telegram-bot**: Official Telegram Bot API wrapper for Python.
- **PostgreSQL**: Robust relational database for data persistence.
- **SQLAlchemy**: ORM (Object Relational Mapper) for elegant database interactions.
- **Asyncpg**: Asynchronous PostgreSQL driver for SQLAlchemy.
- **APScheduler**: Advanced Python Scheduler for managing timed tasks and recurring reminders.
- **python-dotenv**: For managing environment variables securely.
- **dateparser**: For flexible parsing of dates and times from natural language.
- **Docker & Docker Compose**: For containerization, ensuring easy deployment and environment consistency.
- **wait-for-it.sh**: A utility to orchestrate service startup in Docker Compose.

---
---

<h1 align="center">ProductivityHabitsTlgBot (Español)</h1>

<p align="center">
Un bot para gestionar hábitos inteligentes y la productividad personal.
</p>


---

### ➤ Descripción General

- [Resumen](#-resumen)
- [Características y Funcionalidades Clave](#-características-y-funcionalidades-clave)
- [Potencialidades](#-potencialidades)
- [Tecnologías Utilizadas](#-tecnologías-utilizadas)

---

<h2 align="center">🚀 Resumen</h2>

**ProductivityHabitsTlgBot** es un bot de Telegram diseñado para empoderar a los usuarios en el establecimiento de **hábitos inteligentes** y el impulso de su **productividad personal**. Al ofrecer una **gestión de tareas intuitiva** y **recordatorios personalizables**, aspira a ser tu compañero digital para alcanzar tus metas diarias y aspiraciones a largo plazo. Construido con **Python**, **PostgreSQL** y **APScheduler**, este bot proporciona una solución robusta y fiable para la organización personal.

---

<h2 align="center">✨ Características y Funcionalidades Clave</h2>

- **Registro de Usuario Intuitivo**:
    - **Registro de Usuario**: Registra a los nuevos usuarios de forma transparente en su primera interacción.
    - **Configuración de Zona Horaria Interactiva**: Guía a los usuarios a través de un menú paginado de varios pasos (Continente -> País -> Ciudad) para configurar su zona horaria, asegurando que los recordatorios sean siempre puntuales.

- **Gestión Dinámica de Tareas y Hábitos**:
    - **Crear Tareas**: Añade rápidamente nuevas tareas con descripciones y fechas de vencimiento. La frecuencia (una vez, diaria, semanal, etc.) se selecciona mediante un menú de botones interactivo para minimizar errores.
    - **Gestión de Hábitos**: Los usuarios pueden suscribirse a una lista de hábitos predefinidos para recibir recordatorios periódicos.
    - **Listar y Modificar**: Visualiza todas las tareas pendientes, y marca las tareas de única vez como completadas o elimina cualquier tarea.

- **Recordatorios Inteligentes y Conscientes de la Zona Horaria**:
    - Aprovecha **APScheduler** para proporcionar notificaciones a tiempo para todas las tareas y hábitos programados.
    - Todos los recordatorios se adaptan completamente a la zona horaria configurada por cada usuario.
    - Las notificaciones de hábitos pueden ser programadas para múltiples horas del día.

- **Persistencia de Datos**: Utiliza **PostgreSQL** para asegurar que todos los datos de usuario, tareas y suscripciones a hábitos se almacenen de forma segura y persistan a través de los reinicios del bot.

- **Arquitectura Modular y Escalable**: Diseñado con una clara separación de responsabilidades (manejadores, interacciones con la base de datos, utilidades) para facilitar futuras expansiones y el mantenimiento.

---

<h2 align="center">💡 Potencialidades</h2>

**ProductivityHabitsTlgBot** es más que un simple gestor de tareas; es la base para un potente asistente personal. Su potencial puede expandirse para incluir:

- **Interacción de Usuario Mejorada**:
    - **Lenguaje Natural para Fechas**: Implementar `dateparser` para permitir a los usuarios establecer fechas límite con frases como "mañana a las 10am" o "el próximo viernes".
    - **Calendario Interactivo**: Añadir un teclado de calendario como alternativa visual para la selección de fechas.
    - **Notificaciones Granulares**: Permitir a los usuarios darse de baja de recordatorios de hábitos individuales a través de un botón.

- **Funcionalidades Avanzadas de Hábitos y Tareas**:
    - **Seguimiento y Análisis de Hábitos**: Integración más profunda del seguimiento de hábitos con visualización del progreso e informes analíticos (ej. rachas, tasas de finalización).
    - **Hábitos Personalizados**: Permitir a los usuarios crear sus propios hábitos en lugar de solo suscribirse a los predefinidos.
    - **Establecimiento de Metas**: Funcionalidades para definir y seguir metas más grandes desglosadas en tareas más pequeñas.

- **Integraciones e IA**:
    - **Integración con Servicios Externos**: Conexión con calendarios (Google Calendar, Outlook) o aplicaciones de toma de notas.
    - **Sugerencias Impulsadas por IA**: Sugerencias proactivas de tareas u optimización de horarios basadas en el comportamiento del usuario.

- **Comunidad y Gamificación**:
    - **Colaboración en Equipo**: Extensión de la funcionalidad para la gestión de tareas de equipos pequeños y hábitos compartidos.
    - **Gamificación**: Introducción de puntos, insignias o tablas de clasificación para hacer la productividad más atractiva.

---

<h2 align="center">🛠️ Tecnologías Utilizadas</h2>

- **Python**: El lenguaje de programación principal.
- **python-telegram-bot**: Wrapper oficial de la API de Telegram Bot para Python.
- **PostgreSQL**: Base de datos relacional robusta para la persistencia de datos.
- **SQLAlchemy**: ORM (Mapeador Objeto-Relacional) para interacciones elegantes con la base de datos.
- **Asyncpg**: Driver asíncrono de PostgreSQL para SQLAlchemy.
- **APScheduler**: Planificador avanzado de Python para gestionar tareas programadas y recordatorios recurrentes.
- **python-dotenv**: Para la gestión segura de variables de entorno.
- **dateparser**: Para el análisis flexible de fechas y horas a partir de lenguaje natural.
- **Docker y Docker Compose**: Para la contenerización, asegurando una fácil implementación y consistencia del entorno.
- **wait-for-it.sh**: Una utilidad para orquestar el inicio de servicios en Docker Compose.
