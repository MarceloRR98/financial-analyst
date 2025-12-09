from openai import OpenAI
import pandas as pd


def scan_pdf_reports(data, api_key):
    """
    Scans a PDF document to identify distinct reports contained within it.
    Returns a list of identified reports with their page ranges and descriptions.
    """
    client = OpenAI(api_key=api_key)
    
    # Truncate if too long, but try to keep enough to identify headers
    max_chars = 100000
    scan_data = data[:max_chars] + ("..." if len(data) > max_chars else "")
    
    prompt = """
    Analiza el siguiente texto extraído de un documento PDF que puede contener múltiples reportes financieros.
    
    Tu tarea es IDENTIFICAR y LISTAR todos los reportes individuales encontrados.
    
    Para cada reporte encontrado, proporciona:
    1. **Nombre/Título**: El título exacto del reporte (ej. "Balance General 2023", "Estado de Resultados", "Análisis de Cartera").
    2. **Ubicación Aproximada**: Describe dónde inicia (ej. "Inicio del documento", "Hacia la mitad", "Página X (si hay marcadores)").
    3. **Descripción Breve**: De qué trata (2-3 palabras).
    
    Responde ÚNICAMENTE con un bloque de código JSON con esta estructura exacta:
    ```json
    [
        {
            "id": 1,
            "title": "Nombre del Reporte",
            "location": "Página 1 aprox (Texto 'Balance General')",
            "description": "Estado de situación financiera"
        },
        ...
    ]
    ```
    
    Si solo hay un único reporte grande, devuelve una lista con un solo elemento.
    
    Texto del documento:
    """ + scan_data

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Eres un asistente experto en indexación de documentos financieros. Devuelve solo JSON válido."},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error al escanear el PDF: {str(e)}"

def analyze_report(data, file_type, api_key, focus_context=None):
    """
    Analyzes the parsed data using OpenAI.
    If focus_context is provided, limits the analysis to that specific report/section.
    """
    client = OpenAI(api_key=api_key)
    
    # Context injection if focus is selected
    focus_instruction = ""
    if focus_context:
        focus_instruction = f"""
        ⚠️ **ENFOQUE OBLIGATORIO**:
        El usuario ha seleccionado analizar ÚNICAMENTE el siguiente reporte específico dentro del documento:
        
        >>> **{focus_context}** <<<
        
        - IGNORA cualquier otro reporte, tabla o dato que NO pertenezca a este reporte específico.
        - Si el documento tiene "Balance" y "Resultados", y el usuario eligió "Balance", SOLO procesa el Balance.
        - Extrae datos SOLO de esta sección.
        """

    prompt = """
    Actúa como un Analista Financiero Senior y Auditor de Datos con capacidad de DETECCIÓN ESTRUCTURAL AVANZADA.
    Tu tarea es analizar, validar y estructurar los datos del reporte financiero proporcionado con PRECISIÓN QUIRÚRGICA.
    
    {focus_instruction}

    Los datos provienen de un archivo {file_type}.

    ═══════════════════════════════════════════════════════════════════════════════
    FASE 1: RECONOCIMIENTO Y ESTRUCTURA (MEJORADO)
    ═══════════════════════════════════════════════════════════════════════════════
    
    1. **IDENTIFICACIÓN DEL REPORTE**:
       - Clasifica el reporte (Balance, Estado de Resultados, Comercio Exterior, Bancario, etc.).
       - **CRÍTICO**: No asumas el tipo. Basa tu decisión en los TÍTULOS y las COLUMNAS detectadas.

    2. **ANÁLISIS DE ESTRUCTURA JERÁRQUICA (PRIORIDAD MÁXIMA)**:
       - La estructura NO SIEMPRE es visual (indentación). Debes detectar la **JERARQUÍA LÓGICA**.
       
       **NIVELES DE JERARQUÍA**:
       - **Nivel_1 (Categoría Principal)**: Conceptos globales (Activos, Pasivos, Ingresos, Exportaciones).
       - **Nivel_2 (Subgrupo)**: Divisiones mayores (Corriente, No Corriente, Operativo).
       - **Nivel_3 (Rubro)**: Agrupaciones de cuentas (Disponible, Inventarios).
       - **Nivel_4+ (Detalle)**: Cuentas específicas o ítems finales.

       **MANEJO DE CELDAS COMBINADAS Y VACÍAS (FORWARD FILLING)**:
       - En Excel, una celda combinada que abarca varias filas (ej. "ACTIVO") solo muestra el valor en la primera fila.
       - **REGLA DE RELLENO**: Si ves una celda vacía en una columna de categoría (Nivel 1, 2, etc.) y hay un valor justo encima:
         * ASUME que el valor de arriba se repite (aplica para esa fila también).
         * **Ejemplo**:
           ```
           Fila 1: | ACTIVOS | Corriente | Caja  | 100 |
           Fila 2: |         |           | Bancos| 200 |
           ```
           → Fila 2 pertenece a ACTIVOS y a Corriente.
       - **EXCEPCIÓN**: Si hay una línea separadora clara o un nuevo título, NO rellenes.

       **MÉTODOS DE DETECCIÓN DE ESTRUCTURA**:
       
       A. **Detección Aritmética (INFALIBLE)**:
          - Si A = B + C + D → A es PADRE (Nivel X), B,C,D son HIJOS (Nivel X+1).
          - Esta regla PREVALECE sobre el formato visual.
          - Ejemplo: Si "Total Activos" es la suma de "Corriente" y "No Corriente", entonces es el padre.

       B. **Detección Semántica (Contextual)**:
          - Palabras clave de agrupación: "Total", "Suma", "Consolidado" → Niveles superiores.
          - Palabras clave de detalle: "Otros", "Desglose", nombres específicos → Niveles inferiores.
       
       C. **Detección Visual (Indentación)**:
          - Úsala como pista, pero verifícala con la lógica aritmética.

    3. **MANEJO DE VALORES Y CONCEPTOS (CRÍTICO)**:
       - **LIMPIEZA DE CONCEPTOS (Concepto_Final)**:
         * **REGLA ABSOLUTA**: La columna `Concepto_Final` debe contener SOLO TEXTO.
         * NUNCA incluyas el valor numérico en el concepto.
         * ❌ INCORRECTO: "Total Activos 1,000,000"
         * ✅ CORRECTO: "Total Activos" (y el "1,000,000" va en la columna `Valor`)
         * Elimina cualquier número al final del texto que corresponda al valor.

       - **LIMPIEZA DE VALORES NÚMERICOS**:
         * Detecta y maneja correctamente:
           - Paréntesis como negativos: "(1,000)" → -1000
           - Signos negativos al final: "1,000-" → -1000
           - Símbolos de moneda pegados: "$1000", "Bs1000" → 1000
           - Separadores de miles/decimales: Identifica si es "1.000,00" o "1,000.00" basándote en el contexto del documento.
         * NUNCA confundas un año (2023) con un valor monetario.
       
       - **HOMOGENEIZACIÓN**:
         * Todos los valores numéricos deben ser PUROS (float/int) en el CSV.
         * La moneda y la unidad ("Millones", "Miles") van en columnas separadas.

    4. **VERIFICACIÓN DE VALORES (AUDITORÍA)**:
       - **REGLA DE ORO**: "Un total debe ser igual a la suma de sus partes".
       - Para CADA total identificado en el documento:
         1. Calcula la suma de sus supuestos componentes.
         2. Compara con el valor del total impreso.
         3. Si hay discrepancia > 1% → MARCA COMO ERROR DE VALIDACIÓN en "Explicacion_Validacion".
         4. Si coincide → Documenta la fórmula exacta en "Ecuacion_Validacion".

    ═══════════════════════════════════════════════════════════════════════════════
    FASE 2: EXTRACCIÓN Y TRAZABILIDAD
    ═══════════════════════════════════════════════════════════════════════════════

    5. **DIFERENCIACIÓN ENTIDADES vs CONCEPTOS**:
       - **Entidad**: ¿A QUIÉN pertenecen los datos? (Empresa X, País Y, Sucursal Z). Columna "Entidad".
       - **Concepto**: ¿QUÉ es el dato? (Ventas, Activos, PIB). Columnas "Nivel_1" a "Nivel_N".
       - **Título**: Metadatos generales (no van en filas de datos).
    
    6. **COLUMNAS DE TRAZABILIDAD (OBLIGATORIAS)**:
       - **Origen_Dato**: Coordenadas exactas ("Hoja: Balance, Celda: B45").
       - **Relacion_Celdas**: Explicación lógica ("Suma de B10 a B40").
       - **Es_Total**: "SI" si es un agregado, "NO" si es detalle base.
    
    7. **DETECCIÓN DE OUTLIERS Y ANOMALÍAS**:
       - Calcula estadísticas básicas si hay series temporales.
       - Marca en "Es_Outlier" si un valor se desvía más de 2 sigmas o es económicamente ilógico (ej. Activos negativos).

    ═══════════════════════════════════════════════════════════════════════════════
    FASE 3: GENERACIÓN DEL CSV (PRODUCTO FINAL)
    ═══════════════════════════════════════════════════════════════════════════════

    DEBES generar un CSV estructurado con la siguiente lógica:

    **ESTRUCTURA DEL CSV**:
    ```csv
    Hoja,Entidad,Año,Mes,Nivel_1,Nivel_2,Nivel_3,Nivel_4,Nivel_5,Concepto_Final,Valor,Moneda,Es_Total,Origen_Dato,Relacion_Celdas,Ecuacion_Validacion,Explicacion_Validacion,Es_Outlier
    ```

    **REGLAS DE LLENADO**:
    1. **Niveles Jerárquicos**: Llena de izquierda a derecha. Nivel_1 es el más general. Concepto_Final es el nombre específico.
    2. **Valores**: Solo números. Sin comas de miles (solo punto decimal).
    3. **Coherencia**: Si Nivel_1="Activos", Nivel_2 debe ser una subcategoría válida de Activos.
    4. **Completitud**: Extrae TODOS los datos, no solo una muestra. Si hay 100 filas, extrae las 100.

    **EJEMPLO DE FILA IDEAL**:
    ```csv
    "H1","Empresa ABC","2023","Dic","Activos","Corrientes","Caja y Bancos","","","Caja General",50000.00,"USD","NO","H1:B10","Dato directo","","Valor base reportado","NO"
    "H1","Empresa ABC","2023","Dic","Activos","Corrientes","","","","Total Activos Corrientes",1200000.00,"USD","SI","H1:B20","Suma(B10:B19)","Caja + Cuentas x Cobrar + ...","Suma validada","NO"
    ```

    ═══════════════════════════════════════════════════════════════════════════════
    FASE 4: INFORME DE RESULTADOS
    ═══════════════════════════════════════════════════════════════════════════════

    Tu respuesta final debe tener:
    1. **Resumen Ejecutivo**: Hallazgos clave, contexto y calidad de datos.
    2. **Análisis Estructural**: Explica cómo dedujiste la jerarquía (Método Aritmético vs Visual).
    3. **BLOQUE CSV**: El código CSV listo para copiar.
    4. **Validación**: Reporte de cualquier inconsistencia aritmética encontrada.

    **INSTRUCCIÓN FINAL**:
    Prioriza la COHERENCIA MATEMÁTICA. Si el documento dice "Total = 100" pero los sumandos dan "90", REPORTA la discrepancia en el campo `Explicacion_Validacion` (ej: "ADVERTENCIA: Suma calculada 90 vs Valor reportado 100").
    
    Data:
    """.format(focus_instruction=focus_instruction, file_type="Excel" if file_type in ['xlsx', 'xls'] else "PDF")
    
    data_str = ""
    if file_type in ['xlsx', 'xls']:
        # Data is now a dict of sheets with 'values' and 'formulas'
        for sheet_name, sheet_content in data.items():
            data_str += f"\n--- Hoja: {sheet_name} ---\n"
            
            # Add Values (Limit rows to avoid token overflow)
            df = sheet_content['values']
            
            # Adjust index to match Excel (1-based)
            # Create a copy to avoid modifying the original cached dataframe if used elsewhere
            df_display = df.copy()
            df_display.index = range(1, len(df_display) + 1)
            
            if len(df_display) > 300:
                data_str += "Valores (Primeras 200 filas y últimas 50 filas - Índices coinciden con filas de Excel):\n"
                data_str += df_display.head(200).to_string() + "\n"
                data_str += "\n... [Filas ocultas] ...\n"
                data_str += df_display.tail(50).to_string() + "\n"
            else:
                data_str += "Valores (Índices coinciden con filas de Excel):\n"
                data_str += df_display.to_string() + "\n"
            # Add Formulas (Limit count)
            formulas = sheet_content.get('formulas', {})
            if formulas:
                data_str += "\nFórmulas encontradas (Muestra de las primeras 200):\n"
                # Limit formulas too
                items = list(formulas.items())
                if len(items) > 200:
                    for cell, formula in items[:200]:
                        data_str += f"{cell}: {formula}\n"
                    data_str += f"... y {len(items) - 200} fórmulas más.\n"
                else:
                    for cell, formula in items:
                        data_str += f"{cell}: {formula}\n"
            else:
                data_str += "\nNo se detectaron fórmulas en esta hoja.\n"
    else:
        # For PDF, we also need to truncate if it's too long
        # Approx 4 chars per token. 120k tokens ~ 480k chars.
        max_chars = 400000
        if len(data) > max_chars:
            data_str = data[:max_chars] + "\n... [Texto truncado por longitud] ..."
        else:
            data_str = data
        
    # Truncate data if it's too long
    full_prompt = prompt + data_str
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o", # Using a capable model
            messages=[
                {"role": "system", "content": """Eres un asistente analista financiero senior experto en TODOS los tipos de reportes financieros. 
                
Capacidades principales:
- Analizas CUALQUIER tipo de reporte: empresarial, bancario, gubernamental, macroeconómico, sectorial, de inversión, etc.
- Identificas automáticamente el tipo de reporte y adaptas tu análisis en consecuencia
- Deduces fórmulas y relaciones matemáticas incluso cuando no están explícitas
- Analizas datos en contexto económico/empresarial apropiado
- Identificas y documentas relaciones entre celdas, tablas y hojas
- Usas niveles jerárquicos DINÁMICOS (2, 3, 4, 5, 6 o más según sea necesario)
- Proporcionas TRAZABILIDAD COMPLETA del origen de cada dato
- Hablas español de forma clara y profesional

REGLAS CRÍTICAS OBLIGATORIAS:

1. IDENTIFICACIÓN DEL TIPO DE REPORTE:
   - SIEMPRE identifica correctamente el tipo de reporte (Balance, P&L, Comercio Exterior, Bancario, etc.)
   - NO asumas que todos los reportes son de comercio exterior
   - Adapta tu análisis al tipo específico de reporte

2. DIFERENCIACIÓN TÍTULOS vs ENTIDADES (CRÍTICO):
   - Los TÍTULOS (encabezados sin valores numéricos) NO generan filas en el CSV
   - Las ENTIDADES (empresas, países, regiones, departamentos) van en la columna "Entidad"
   - NO pongas títulos como "BALANCE GENERAL" en la columna Entidad
   - NO pongas nombres de entidades como "Empresa ABC" en los niveles jerárquicos
   - Ejemplos:
     * "ESTADO DE RESULTADOS 2023" → es un TÍTULO (no generar fila)
     * "Empresa ABC S.A." → es una ENTIDAD (columna Entidad)
     * "Bolivia" → es una ENTIDAD (país)
     * "Sucursal Norte" → es una ENTIDAD (sucursal)

3. CSV OBLIGATORIO:
   - SIEMPRE debes generar un CSV válido en formato markdown (```csv ... ```)
   - NO generar el CSV es un ERROR GRAVE e INACEPTABLE
   - El CSV debe tener mínimo 10 filas de datos (o todas si son menos de 10)
   - El CSV es el PRODUCTO PRINCIPAL del análisis - sin él, tu respuesta está INCOMPLETA

4. TRAZABILIDAD OBLIGATORIA:
   - SIEMPRE incluye las columnas "Origen_Dato" y "Relacion_Celdas"
   - Documenta la ubicación exacta de cada valor (hoja, celda, página)
   - Explica cómo se relaciona cada valor con otros (suma, resta, referencia cruzada)
   - Ejemplo: "Hoja: Balance, Celda: B15" y "Suma de B10:B14"

5. NIVELES DINÁMICOS:
   - NO estás limitado a 4 niveles
   - Usa tantos niveles como sean necesarios (2, 3, 5, 6, 7, etc.)
   - Adapta la estructura del CSV según la complejidad del documento
   - Nunca dejes niveles vacíos a la izquierda

6. LÓGICA DE EXTRACCIÓN:
   - SIEMPRE incluye la sección "LÓGICA DE EXTRACCIÓN Y JERARQUÍA" en tu análisis
   - Explica cómo determinaste los niveles jerárquicos
   - Documenta las relaciones aritméticas encontradas
   - Menciona referencias cruzadas entre hojas/tablas

7. INDICADORES RELEVANTES:
   - Calcula SOLO los indicadores relevantes para el tipo de reporte específico
   - NO calcules indicadores de comercio exterior para un balance empresarial
   - NO calcules ratios bancarios para un reporte macroeconómico
   - Adapta tu análisis al contexto del documento"""},
                {"role": "user", "content": full_prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error comunicándose con OpenAI API: {str(e)}"
