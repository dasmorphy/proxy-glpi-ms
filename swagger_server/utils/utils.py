from datetime import date, datetime, time, timedelta
from pytz import timezone
import re

from sqlalchemy import or_

from swagger_server.models.db.logbook_entry import LogbookEntry
from swagger_server.models.db.logbook_out import LogbookOut

# Funciones de utilidad para el sistema completo.

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

SEARCH_COLUMNS_OUT = [
    LogbookOut.name_user,
    LogbookOut.name_driver,
    LogbookOut.truck_license,
    LogbookOut.shipping_guide,
    LogbookOut.observations,
    LogbookOut.authorized_by,
    LogbookOut.destiny,
]

SEARCH_COLUMNS_ENTRY = [
    LogbookEntry.name_user,
    LogbookEntry.name_driver,
    LogbookEntry.truck_license,
    LogbookEntry.shipping_guide,
    LogbookEntry.observations,
    LogbookEntry.authorized_by,
    LogbookEntry.destiny_intern,
]

PREFIX_RE = re.compile(
    r'^(Ing\.?|Dr\.?|Dra\.?|Sr\.?|Sra\.?|Tnt\.?|Tte\.?|Cap\.?|Crnel\.?|Arq\.?|Eco\.?)\s+',
    re.IGNORECASE,
)

WHITELIST: dict[str, dict] = {
    'Achibros': {
        'positions': ['Gerente', 'Jefe De Seguridad', 'Otro'],
        'contacts':  ['Carlos José Achi', 'Danny Delgado'],
    },
    'Acuamarcruz': {
        'positions': ['Administrador', 'Otro'],
        'contacts':  ['Alejandro Cruz'],
    },
    'Acvipac': {
        'positions': ['Gerente General', 'Otro'],
        'contacts':  ['Gabriela Romero'],
    },
    'Adelca': {
        'positions': ['Jefe De Seguridad', 'Otro'],
        'contacts':  ['Edguin Mosquera'],
    },
    'Agripac': {
        'positions': ['Jefe De Seguridad Agripac', 'Otro'],
        'contacts':  ['Bruno Cerezo'],
    },
    'Aifa': {
        'positions': ['Gerente  De Operaciones', 'Gerente Rrhh', 'Otro'],
        'contacts':  ['Héctor Quinteros', 'Daniel Espinoza'],
    },
    'Ana Brito': {
        'positions': ['Propietario', 'Otro'],
        'contacts':  ['Ana Brito'],
    },
    'Anisaleo': {
        'positions': ['Gerente', 'Otro'],
        'contacts':  ['Juan Paulo Maruri'],
    },
    'Antes Nicovita': {
        'positions': ['Jefe De Seguridad', 'Otro'],
        'contacts':  ['Johnny Garcia'],
    },
    'Aq1': {
        'positions': ['Finanzas', 'Gerente General', 'Otro'],
        'contacts':  ['Jerrie Jalon', 'Eduardo Huren'],
    },
    'Aquagen': {
        'positions': ['Gerente', 'Jefe De Seguridad', 'Otro'],
        'contacts':  ['Luís Francisco Burgos', 'Marlon Martínez'],
    },
    'Aqualitoral': {
        'positions': ['Administrativo', 'Jefe De Producción', 'Otro'],
        'contacts':  ['Nicolás Pesantez', 'Andrés Guerrero'],
    },
    'Aray': {
        'positions': ['Administrador', 'Otro'],
        'contacts':  ['Juan José Saab'],
    },
    'Arrocera La Palma': {
        'positions': ['Gerente General', 'Otro'],
        'contacts':  ['Isidro Calderon'],
    },
    'Asoc Camararoneros Puna': {
        'positions': ['Gerente General', 'Otro'],
        'contacts':  ['Pablo Perez'],
    },
    'Avicacompany': {
        'positions': ['Gerente General', 'Otro'],
        'contacts':  ['Alex Cabrera'],
    },
    'Barrecallebaut': {
        'positions': ['Compras', 'Proyectos', 'Otro'],
        'contacts':  ['Karen Cortez', 'Kevin Jativa'],
    },
    'Bellitec': {
        'positions': ['Gerente Administrativa', 'Gerente General', 'Otro'],
        'contacts':  ['Héctor Madero', 'Miguel Aguilar', 'Oswaldo Borja', 'Johana Farah'],
    },
    'Biomar': {
        'positions': ['Jefe De Seguridad', 'Proyectos', 'Seguridad Instrial', 'Otro'],
        'contacts':  ['Dick Aguilar', 'Enrique Romero', 'Manuel Orellana'],
    },
    'Bohman': {
        'positions': ['Administrador', 'Otro'],
        'contacts':  ['Ruben Ramirez'],
    },
    'Boludcorp': {
        'positions': ['Gerente General', 'Otro'],
        'contacts':  ['Ana Moreno'],
    },
    'Brumesa': {
        'positions': ['Jefe De Operaciones', 'Otro'],
        'contacts':  ['Armando Maza'],
    },
    'Caamronera': {
        'positions': ['Dueño', 'Gerente General', 'Otro'],
        'contacts':  ['Francisco Parra', 'Milton Paredes'],
    },
    'Cahusa': {
        'positions': ['Gerente General', 'Otro'],
        'contacts':  ['Ricardo Menéndez'],
    },
    'Camajose': {
        'positions': ['Administrador', 'Gerente', 'Otro'],
        'contacts':  ['Jose Gonzalez', 'José González'],
    },
    'Camarimp': {
        'positions': ['Gerente General', 'Otro'],
        'contacts':  ['Franklin Contreras'],
    },
    'Camaron Mar': {
        'positions': ['Gerente General', 'Otro'],
        'contacts':  ['Andrés Botero'],
    },
    'Camarondeli': {
        'positions': ['Jefe De Seguridad', 'Otro'],
        'contacts':  ['Jorge Pazmiño'],
    },
    'Camaronera Esmeralda': {
        'positions': ['Gerente General', 'Otro'],
        'contacts':  ['Daniel Aguilera'],
    },
    'Camaronera Puna': {
        'positions': ['Gerente General', 'Otro'],
        'contacts':  ['Andres Ruiz'],
    },
    'Camaronera Rapasinc': {
        'positions': ['Gerente General', 'Otro'],
        'contacts':  ['Freddy Chiang'],
    },
    'Camaronera San Vicente': {
        'positions': ['Gerente General', 'Otro'],
        'contacts':  ['Silvio Andrade', 'Silvia Macias'],
    },
    'Camaronera Taleb': {
        'positions': ['Gerente General', 'Otro'],
        'contacts':  ['Henrry Taleb'],
    },
    'Camaronera Taura': {
        'positions': ['Gerente General', 'Otro'],
        'contacts':  ['David Villalobos'],
    },
    'Camaronero': {
        'positions': ['Gerente General', 'Otro'],
        'contacts':  ['Ernesto Vera Bernabe'],
    },
    'Camaronmar': {
        'positions': ['Gerente General', 'Otro'],
        'contacts':  ['Andrés Botero'],
    },
    'Campamento Victoria': {
        'positions': ['Administrador', 'Otro'],
        'contacts':  ['Luigi Purizaga'],
    },
    'Cargill': {
        'positions': ['Logistica', 'Proyectos', 'Otro'],
        'contacts':  ['Geovanny Villamar', 'Ivanna Aguilar'],
    },
    'Ceibos Procolinas': {
        'positions': ['Administrador', 'Otro'],
        'contacts':  ['Danilo Pozo'],
    },
    'Cepec': {
        'positions': ['Gerente De Operaciones', 'Otro'],
        'contacts':  ['Leonardo Mosquera'],
    },
    'Cofimar': {
        'positions': ['Gerente Financiero', 'Jefe De Seguridad', 'Otro'],
        'contacts':  ['Erwin Andre', 'Francisco Pesantes'],
    },
    'Comexport': {
        'positions': ['Jefe Administración Y Financiero', 'Jefe De Seguridad Industrial', 'Otro'],
        'contacts':  ['Deniss Arévalo', 'Álvaro Villalba'],
    },
    'Construdipro Mallorca': {
        'positions': ['Gerente De Logística', 'Gerente De Mantenimiento', 'Otro'],
        'contacts':  ['Elicio Chiriboga', 'Christian Galarza'],
    },
    'Corporacion Lanec': {
        'positions': ['Gerente De Agricolas', 'Gerente General', 'Jefe De Seguridad', 'Operaciones', 'Sistemas', 'Otro'],
        'contacts':  ['Cristóforo', 'Darwin Pincay', 'Danny Velez', 'Federico Estupiñan', 'Paul Olsen', 'Renzo Olsen'],
    },
    'Crisomar': {
        'positions': ['Propietario', 'Otro'],
        'contacts':  ['Bastian Hurtado'],
    },
    'Culsaro': {
        'positions': ['Administrador', 'Gerente Seguridad', 'Otro'],
        'contacts':  ['Luis Pilay', 'Ricardo Zambrano'],
    },
    'Dbfshrimp': {
        'positions': ['Operativo', 'Otro'],
        'contacts':  ['Gannio Dumes'],
    },
    'Ecuaquimica': {
        'positions': ['Jefe De Compras', 'Jefe De Seguridad Industrial', 'Otro'],
        'contacts':  ['Juan Pablo Padilla', 'Nelson Yepez', 'David Vaca'],
    },
    'Equitransa': {
        'positions': ['Gerente General', 'Otro'],
        'contacts':  ['Hector Catagua'],
    },
    'Escuvi': {
        'positions': ['Gerente General', 'Otro'],
        'contacts':  ['Fabricio Ferreti'],
    },
    'Expalsa': {
        'positions': ['Compras', 'Gerente Compras', 'Jefe De Seguridad', 'Operaciones', 'Otro'],
        'contacts':  ['Aldo Centanaro', 'Jose Vite', 'Keyla Branque', 'Rafael Avila', 'Sebastian Malo'],
    },
    'Farmagro': {
        'positions': ['Jefe De Seguridad', 'Jefe De Sucursales', 'Otro'],
        'contacts':  ['Cesar Carpio', 'Cristhian Steiner'],
    },
    'Filacas': {
        'positions': ['Gerente General', 'Otro'],
        'contacts':  ['Ricardo Menendez'],
    },
    'Fimasa': {
        'positions': ['Director De Seguridad', 'Gerente General', 'Jefe De Seguridad', 'Otro'],
        'contacts':  ['Luis Burgos', 'Marlon Martínez', 'José Chala'],
    },
    'Forquarz': {
        'positions': ['Gerente General', 'Otro'],
        'contacts':  ['Humberto Lopez'],
    },
    'Grupo Almar': {
        'positions': ['Gerente De Seguridad', 'Jefe De Seguridad', 'Otro'],
        'contacts':  ['Daniel Flores', 'Marcelo Villareal'],
    },
    'Grupo Champmar': {
        'positions': ['Gerente De Seguridad', 'Gerente Operaciones', 'Jefe De Seguridad', 'Otro'],
        'contacts':  ['Ezequiel Alfonseca', 'Felix Freire', 'Juan Pablo Guerrero'],
    },
    'Grupo Espinoza: Acuataura': {
        'positions': ['Asistente Contable', 'Otro'],
        'contacts':  ['Diana Pinela'],
    },
    'Grupo Fajardo': {
        'positions': ['Compras', 'Otro'],
        'contacts':  ['Karla Iturralde'],
    },
    'Grupo Pino': {
        'positions': ['Administrador', 'Gerente', 'Gerente General', 'Jefe De Seguridad', 'Otro'],
        'contacts':  ['Alvaro Pino', 'Álvaro Pino', 'Alberto Pino', 'Jorge Robalino', 'Cesar Acosta'],
    },
    'Grupo Santos': {
        'positions': ['Asistente De Gerencia', 'Secretaria', 'Otro'],
        'contacts':  ['Yulexy Perez', 'Yulexi Perez'],
    },
    'Grupo Varsa': {
        'positions': ['Jefede Seguridad', 'Otro'],
        'contacts':  ['Cristian Mendoza'],
    },
    'Grupo Vasco': {
        'positions': ['Gerente General', 'Jefe De Seguridad', 'Sistemas', 'Otro'],
        'contacts':  ['Cristian Mendoza', 'Bryan Valarezo', 'Mathias Egugerin'],
    },
    'Hacienda Palo Santo': {
        'positions': ['Administrador', 'Otro'],
        'contacts':  ['Manuel Moron'],
    },
    'Hcda Victoria': {
        'positions': ['Gerente General', 'Otro'],
        'contacts':  ['Harry Olsen'],
    },
    'Hotel Wyndham Manta': {
        'positions': ['Administrador', 'Otro'],
        'contacts':  ['David Guijarro'],
    },
    'Impala Terminal': {
        'positions': ['Jefe Operaciones', 'Otro'],
        'contacts':  ['Bryron Vivanco', 'Byron Vivanco'],
    },
    'Impala Terminals': {
        'positions': ['Administrador', 'Otro'],
        'contacts':  ['Byron Vivanco'],
    },
    'Indurama': {
        'positions': ['Gerente Seguridad', 'Otro'],
        'contacts':  ['Gustavo Torres'],
    },
    'Ingenio La Troncal': {
        'positions': ['Gerente De Seguridad', 'Otro'],
        'contacts':  ['Bruno Moreno'],
    },
    'Ingenio San Carlos': {
        'positions': ['Jefe De Seguridad Ingenio San Carlos', 'Supervisor Seguridad', 'Otro'],
        'contacts':  ['Alexis Macías', 'Patricio Vallejo'],
    },
    'Intercia Inmaconsa': {
        'positions': ['Gerente Administración', 'Otro'],
        'contacts':  ['Tanya Gonzales'],
    },
    'Iriscorp': {
        'positions': ['Gerente General', 'Otro'],
        'contacts':  ['Henrry Palacios'],
    },
    'Junta Beneficiencia De Gye': {
        'positions': ['Gerente De Seguridad', 'Otro'],
        'contacts':  ['Yander Daniel Cano Menéndez'],
    },
    'La Chola': {
        'positions': ['Sistemas', 'Otro'],
        'contacts':  ['Guillermo Zambrano'],
    },
    'La Fabril': {
        'positions': ['Coordinador De Seguridad Física', 'Gerente Administrativo', 'Otro'],
        'contacts':  ['Jhon Borbor Vivero', 'Nataly Marchan'],
    },
    'Lan Harris': {
        'positions': ['Administrador', 'Otro'],
        'contacts':  ['Dan Palau'],
    },
    'Lanec Costa': {
        'positions': ['Jefe De Seguridad', 'Otro'],
        'contacts':  ['Federico Estupiñan'],
    },
    'Lanec Taura': {
        'positions': ['Jefe De Seguridad', 'Otro'],
        'contacts':  ['Willyam Martinez'],
    },
    'Lukmar': {
        'positions': ['Jefe De Seguridad', 'Operaciones', 'Otro'],
        'contacts':  ['Marco Loza', 'Marcos Loza', 'Salvador Briz'],
    },
    'Magic Flower': {
        'positions': ['Gerente General', 'Otro'],
        'contacts':  ['Esteban Saenz'],
    },
    'Malabrigo - Forquarts': {
        'positions': ['Propietario', 'Otro'],
        'contacts':  ['Humberto Lopez'],
    },
    'Maquirental': {
        'positions': ['Administrador', 'Gerente General', 'Otro'],
        'contacts':  ['Aurelio Panchana'],
    },
    'Marco Castillo': {
        'positions': ['Propietario', 'Otro'],
        'contacts':  ['Marco Castillo'],
    },
    'Marprovelsa': {
        'positions': ['Jefe De Seguridad', 'Otro'],
        'contacts':  ['William Jordán', 'George Prado'],
    },
    'Mars': {
        'positions': ['Sistemas', 'Otro'],
        'contacts':  ['Fernando Castro'],
    },
    'Metabaz': {
        'positions': ['Administrador', 'Seguridad', 'Otro'],
        'contacts':  ['Guillermo Garcia', 'Guillermo García'],
    },
    'Molino Champion': {
        'positions': ['Jefe De Seguridad', 'Otro'],
        'contacts':  ['Daniel Pintado'],
    },
    'Muebles El Bosque': {
        'positions': ['Seguridad Industrial', 'Otro'],
        'contacts':  ['Darwin Pisco'],
    },
    'Naturisa': {
        'positions': ['Gerente Seguridad', 'Otro'],
        'contacts':  ['Ricardo Sola Jr'],
    },
    'Novocentro': {
        'positions': ['Gerente De Compra', 'Otro'],
        'contacts':  ['Fiorella Mendoza'],
    },
    'Numa': {
        'positions': ['Administrador', 'Otro'],
        'contacts':  ['Nicolás Romero'],
    },
    'Obrythor -Tauramar - Camartua': {
        'positions': ['Administrador', 'Otro'],
        'contacts':  ['Robert Conforme'],
    },
    'Obrytror': {
        'positions': ['Gerente General', 'Otro'],
        'contacts':  ['Xavier Farah'],
    },
    'Omarsa': {
        'positions': ['Compras', 'Gerente Seguridad', 'Jefe De Seguridad', 'Seguridad Fisica', 'Sistemas', 'Otro'],
        'contacts':  ['Carlos Franco', 'Euclides Bozada', 'Gerardo Chavez', 'Jorge Segovia', 'Juan Franco', 'Luis Piguave', 'Maria Eugenia Procel', 'Scott Dally'],
    },
    'Pacifican Taura': {
        'positions': ['Encargado De Finca Y Sistemas', 'Otro'],
        'contacts':  ['Jimmy Gotaire'],
    },
    'Palmaplast': {
        'positions': ['Operativo', 'Otro'],
        'contacts':  ['Freddy Angel'],
    },
    'Pesalmar': {
        'positions': ['Jefe De Seguridad', 'Otro'],
        'contacts':  ['Juan Carlos Mejía'],
    },
    'Pescasol': {
        'positions': ['Operativo', 'Propietario', 'Otro'],
        'contacts':  ['Jorge Santos', 'Nadia Arteaga'],
    },
    'Pesquesol': {
        'positions': ['Gerente General', 'Otro'],
        'contacts':  ['Yeo Suong'],
    },
    'Pesquesol - Contorto': {
        'positions': ['Administrador', 'Otro'],
        'contacts':  ['Nadia Arreaga'],
    },
    'Pinturas Unidas': {
        'positions': ['Jefe De Seguridad Industrial', 'Otro'],
        'contacts':  ['Alberto Espinoza'],
    },
    'Planta Durancocoa': {
        'positions': ['Gerente General', 'Otro'],
        'contacts':  ['Ricardo Zambrano'],
    },
    'Procolinas': {
        'positions': ['Jefe De Seguridad', 'Otro'],
        'contacts':  ['Pablo Corozo'],
    },
    'Promarisco': {
        'positions': ['Sistemas', 'Otro'],
        'contacts':  ['Cristian Cespedes'],
    },
    'Promariscos': {
        'positions': ['Gerente Seguridad', 'Otro'],
        'contacts':  ['Fernando Cabrera'],
    },
    'Provexpo': {
        'positions': ['Administrador', 'Otro'],
        'contacts':  ['Wilfrido Cardenas'],
    },
    'Pycca': {
        'positions': ['Jefe De Seguridad', 'Otro'],
        'contacts':  ['Darwin Huayamave'],
    },
    'Santa Priscila': {
        'positions': ['Gerente Seguridad', 'Otro'],
        'contacts':  ['Cristian Correa'],
    },
    'Seagate': {
        'positions': ['Gerente General', 'Jefe De Seguridad', 'Otro'],
        'contacts':  ['Elias Neme', 'Elías Neme', 'Alberto Bustamante'],
    },
    'Songa': {
        'positions': ['Seguridad', 'Sistemas', 'Otro'],
        'contacts':  ['Franklin Mosquera', 'Mario Villalta'],
    },
    'Stonmelcorp': {
        'positions': ['Gerente General', 'Otro'],
        'contacts':  ['Rolando Quinde'],
    },
    'Tld Terminal Logístico Durán': {
        'positions': ['Asistente Administrativo', 'Gerente General', 'Otro'],
        'contacts':  ['Fabián Prieto', 'Cristian Preciado'],
    },
    'Tropac': {
        'positions': ['Operativo', 'Otro'],
        'contacts':  ['Marcos Garnica'],
    },
    'Tumbes Pa': {
        'positions': ['Administrador', 'Gerente General', 'Otro'],
        'contacts':  ['Ernesto Quiroz'],
    },
}

CONTACTS_BY_CLIENT: dict[str, list[str]] = {
    'Achibros': ['Carlos José Achi', 'Danny Delgado'],
    'Acuamarcruz': ['Alejandro Cruz'],
    'Acvipac': ['Gabriela Romero'],
    'Adelca': ['Edguin Mosquera'],
    'Agripac': ['Bruno Cerezo'],
    'Aifa': ['Héctor Quinteros', 'Daniel Espinoza'],
    'Ana Brito': ['Ana Brito'],
    'Anisaleo': ['Juan Paulo Maruri'],
    'Antes Nicovita': ['Johnny Garcia'],
    'Aq1': ['Jerrie Jalon', 'Eduardo Huren'],
    'Aquagen': ['Luís Francisco Burgos', 'Marlon Martínez'],
    'Aqualitoral': ['Nicolás Pesantez', 'Andrés Guerrero'],
    'Aray': ['Juan José Saab'],
    'Arrocera La Palma': ['Isidro Calderon'],
    'Asoc Camararoneros Puna': ['Pablo Perez'],
    'Avicacompany': ['Alex Cabrera'],
    'Barrecallebaut': ['Karen Cortez', 'Kevin Jativa'],
    'Bellitec': ['Héctor Madero', 'Miguel Aguilar', 'Oswaldo Borja', 'Johana Farah'],
    'Biomar': ['Dick Aguilar', 'Enrique Romero', 'Manuel Orellana'],
    'Bohman': ['Ruben Ramirez'],
    'Boludcorp': ['Ana Moreno'],
    'Brumesa': ['Armando Maza'],
    'Caamronera': ['Francisco Parra', 'Milton Paredes'],
    'Cahusa': ['Ricardo Menéndez'],
    'Camajose': ['Jose Gonzalez', 'José González'],
    'Camarimp': ['Franklin Contreras'],
    'Camaron Mar': ['Andrés Botero'],
    'Camarondeli': ['Jorge Pazmiño'],
    'Camaronera Esmeralda': ['Daniel Aguilera'],
    'Camaronera Puna': ['Andres Ruiz'],
    'Camaronera Rapasinc': ['Freddy Chiang'],
    'Camaronera San Vicente': ['Silvio Andrade', 'Silvia Macias'],
    'Camaronera Taleb': ['Henrry Taleb'],
    'Camaronera Taura': ['David Villalobos'],
    'Camaronero': ['Ernesto Vera Bernabe'],
    'Camaronmar': ['Andrés Botero'],
    'Campamento Victoria': ['Luigi Purizaga'],
    'Cargill': ['Geovanny Villamar', 'Ivanna Aguilar'],
    'Ceibos Procolinas': ['Danilo Pozo'],
    'Cepec': ['Leonardo Mosquera'],
    'Cofimar': ['Erwin Andre', 'Francisco Pesantes'],
    'Comexport': ['Deniss Arévalo', 'Álvaro Villalba'],
    'Construdipro Mallorca': ['Elicio Chiriboga', 'Christian Galarza'],
    'Corporacion Lanec': ['Cristóforo', 'Darwin Pincay', 'Danny Velez', 'Federico Estupiñan', 'Paul Olsen', 'Renzo Olsen'],
    'Crisomar': ['Bastian Hurtado'],
    'Culsaro': ['Luis Pilay', 'Ricardo Zambrano'],
    'Dbfshrimp': ['Gannio Dumes'],
    'Ecuaquimica': ['Juan Pablo Padilla', 'Nelson Yepez', 'David Vaca'],
    'Equitransa': ['Hector Catagua'],
    'Escuvi': ['Fabricio Ferreti'],
    'Expalsa': ['Aldo Centanaro', 'Jose Vite', 'Keyla Branque', 'Rafael Avila', 'Sebastian Malo'],
    'Farmagro': ['Cesar Carpio', 'Cristhian Steiner'],
    'Filacas': ['Ricardo Menendez'],
    'Fimasa': ['Luis Burgos', 'Marlon Martínez', 'José Chala'],
    'Forquarz': ['Humberto Lopez'],
    'Grupo Almar': ['Daniel Flores', 'Marcelo Villareal'],
    'Grupo Champmar': ['Ezequiel Alfonseca', 'Felix Freire', 'Juan Pablo Guerrero'],
    'Grupo Espinoza: Acuataura': ['Diana Pinela'],
    'Grupo Fajardo': ['Karla Iturralde'],
    'Grupo Pino': ['Alvaro Pino', 'Álvaro Pino', 'Alberto Pino', 'Jorge Robalino', 'Cesar Acosta'],
    'Grupo Santos': ['Yulexy Perez', 'Yulexi Perez'],
    'Grupo Varsa': ['Cristian Mendoza'],
    'Grupo Vasco': ['Cristian Mendoza', 'Bryan Valarezo', 'Mathias Egugerin'],
    'Hacienda Palo Santo': ['Manuel Moron'],
    'Hcda Victoria': ['Harry Olsen'],
    'Hotel Wyndham Manta': ['David Guijarro'],
    'Impala Terminal': ['Bryron Vivanco', 'Byron Vivanco'],
    'Impala Terminals': ['Byron Vivanco'],
    'Indurama': ['Gustavo Torres'],
    'Ingenio La Troncal': ['Bruno Moreno'],
    'Ingenio San Carlos': ['Alexis Macías', 'Patricio Vallejo'],
    'Intercia Inmaconsa': ['Tanya Gonzales'],
    'Iriscorp': ['Henrry Palacios'],
    'Junta Beneficiencia De Gye': ['Yander Daniel Cano Menéndez'],
    'La Chola': ['Guillermo Zambrano'],
    'La Fabril': ['Jhon Borbor Vivero', 'Nataly Marchan'],
    'Lan Harris': ['Dan Palau'],
    'Lanec Costa': ['Federico Estupiñan'],
    'Lanec Taura': ['Willyam Martinez'],
    'Lukmar': ['Marco Loza', 'Marcos Loza', 'Salvador Briz'],
    'Magic Flower': ['Esteban Saenz'],
    'Malabrigo - Forquarts': ['Humberto Lopez'],
    'Maquirental': ['Aurelio Panchana'],
    'Marco Castillo': ['Marco Castillo'],
    'Marprovelsa': ['William Jordán', 'George Prado'],
    'Mars': ['Fernando Castro'],
    'Metabaz': ['Guillermo Garcia', 'Guillermo García'],
    'Molino Champion': ['Daniel Pintado'],
    'Muebles El Bosque': ['Darwin Pisco'],
    'Naturisa': ['Ricardo Sola Jr'],
    'Novocentro': ['Fiorella Mendoza'],
    'Numa': ['Nicolás Romero'],
    'Obrythor -Tauramar - Camartua': ['Robert Conforme'],
    'Obrytror': ['Xavier Farah'],
    'Omarsa': ['Carlos Franco', 'Euclides Bozada', 'Gerardo Chavez', 'Jorge Segovia', 'Juan Franco', 'Luis Piguave', 'Maria Eugenia Procel', 'Scott Dally'],
    'Pacifican Taura': ['Jimmy Gotaire'],
    'Palmaplast': ['Freddy Angel'],
    'Pesalmar': ['Juan Carlos Mejía'],
    'Pescasol': ['Jorge Santos', 'Nadia Arteaga'],
    'Pesquesol': ['Yeo Suong'],
    'Pesquesol - Contorto': ['Nadia Arreaga'],
    'Pinturas Unidas': ['Alberto Espinoza'],
    'Planta Durancocoa': ['Ricardo Zambrano'],
    'Procolinas': ['Pablo Corozo'],
    'Promarisco': ['Cristian Cespedes'],
    'Promariscos': ['Fernando Cabrera'],
    'Provexpo': ['Wilfrido Cardenas'],
    'Pycca': ['Darwin Huayamave'],
    'Santa Priscila': ['Cristian Correa'],
    'Seagate': ['Elias Neme', 'Elías Neme', 'Alberto Bustamante'],
    'Songa': ['Franklin Mosquera', 'Mario Villalta'],
    'Stonmelcorp': ['Rolando Quinde'],
    'Tld Terminal Logístico Durán': ['Fabián Prieto', 'Cristian Preciado'],
    'Tropac': ['Marcos Garnica'],
    'Tumbes Pa': ['Ernesto Quiroz'],
}


def format_uri_connection(connection):
    return connection["DRIVER"] \
        + "+" \
        + connection["LIBRARY"] \
        + "://" \
        + connection["USER"] \
        + ":" \
        + connection["PASSWORD"] \
        + "@" \
        + connection["HOST"] \
        + ":" \
        + connection["PORT"] \
        + "/" \
        + connection["DB"]


def filter_dict(dict, fields):
    # Filtra el diccionario entrante, retornando nuevo diccionario
    # sólo con los campos definidos y descartando los demás.

    filtered_dict = {}

    for key in dict:

        if key in fields:
            filtered_dict[key] = dict[key]

    return filtered_dict


def format_date(datetime):
    # Retorna una representación en String de una fecha/hora dada.

    return datetime.strftime(DATE_FORMAT)


def get_current_datetime():
    # Retorna la fecha actual en su correspondiente timezone

    return datetime.now(timezone('America/Guayaquil'))


def check_email(email):
    """
    Valida el email

    Args:
        email (String): correo electronico

    Returns:
        True or False si mail es valido o invalido
    """
    regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    if (re.fullmatch(regex, email)):
        return True
    else:
        return False
    
def get_date_range(fecha_inicio=None, fecha_fin=None):
    if fecha_inicio and fecha_fin:
        return fecha_inicio, fecha_fin

    today = date.today()
    start = datetime.combine(today, datetime.min.time())
    end = start + timedelta(days=1)

    return start, end

def get_workday() -> str :
    now = datetime.now().time()

    if time(7, 0) <= now < time(19, 0):
        return "Diurna"
    else:
        return "Nocturna"

def parse_filters(headers, params):
    groups = headers.get("groups-business-id")
    sectors = headers.get("sectors")
    workday = headers.get("workday")
    category_ids = headers.get("ids-categories")
    return {
        "id_logbook": headers.get("id-logbook"),
        "user": headers.get("user"),
        "groups_business_id": [int(x) for x in groups.split(",")] if groups else [],
        "employees_intern": [int(x) for x in headers.get("employees-intern", "").split(",") if x],
        "start_date": params.get("start_date"),
        "end_date": params.get("end_date"),
        "sector_id": [int(x) for x in sectors.split(",")] if sectors else [],
        "category_ids": [int(x) for x in category_ids.split(",")] if category_ids else [],
        "workday": [x for x in workday.split(",")] if workday else [],
        "id_business": params.get("id_business"),
        "notCategory": headers.get("notCategory"),
        "search": params.get("search", "").strip() or None,
    }

def apply_search(filters: list, search: str, columns: list):
    """Agrega un OR con ILIKE sobre todas las columnas especificadas."""
    if not search:
        return
    
    term = f"%{search}%"
    filters.append(
        or_(*[col.ilike(term) for col in columns])
    )

def diference_time(logbook_entry, logbook_out):

    try:
        date_entry = logbook_entry.created_at
        date_out = logbook_out.created_at

        # Diferencia
        difference = date_out - date_entry

        total_seconds = int(difference.total_seconds())

        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60

        return f"{days}d {hours}h {minutes}m"
    
    except Exception as exp:
        print(exp)
        return None


def serialize_out(out, group_name, id_sector, name_sector, name_category, images_out):
    if out is None:
        return None
    return {
        "id_logbook_out": out.id_logbook_out,
        "unity_id": out.unity_id,
        "category_id": out.category_id,
        "name_user": out.name_user,
        "group_name": group_name,
        "group_business_id": out.group_business_id,
        "shipping_guide": out.shipping_guide,
        "quantity": out.quantity,
        "weight": out.weight,
        "truck_license": out.truck_license,
        "name_driver": out.name_driver,
        "lat": out.lat,
        "long": out.long,
        "person_withdraws": out.person_withdraws,
        "destiny": out.destiny,
        "authorized_by": out.authorized_by,
        "observations": out.observations,
        "created_at": out.created_at,
        "updated_at": out.updated_at,
        "created_by": out.created_by,
        "updated_by": out.updated_by,
        "workday": out.workday,
        "id_sector": id_sector,
        "name_sector": name_sector,
        "name_category": name_category,
        "images_out": images_out or [],
        "status": "Finalizado"
    }
