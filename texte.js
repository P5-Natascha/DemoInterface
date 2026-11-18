/* =====================================================================
   TEXTE UND EINSTELLUNGEN
   Hier steht alles, was auf der Seite zu lesen ist. Einfach den Text
   zwischen den Anführungszeichen ändern. "\n" ergibt einen Zeilenumbruch.
   Die Form der Seite (Farben, Layout) steht in style.css.
   ===================================================================== */
const EINSTELLUNGEN = {
  githubLink: 'https://github.com/orgs/P5-Natascha/repositories',   // hier den GitHub-Link eintragen
  yAchseUmkehren: false,   // true, falls "hoch" am Auto den Wert 0 statt 4095 bedeuten soll
};

const TEXTE = {
  seitentitel: 'Natascha – P5-Fahrroboter live im Browser steuern',   // Text im Browser-Tab

  kopfzeile: {
    name: 'Natascha · P5-Fahrroboter',
    menue: {
      kameras: 'Kameras',
      telemetrie: 'Telemetrie',
      technik: 'So funktioniert’s',
      projekt: 'Das Projekt',
    },
    githubKnopf: 'GitHub',
  },

  start: {
    titel: 'Ein Kinderauto.\nSelbst umgebaut.\nVom Handy aus ferngesteuert.',
    einleitung: 'Natascha ist unser P5-Fahrroboter: ein Auto, in dem sonst Kinder sitzen, umgebaut mit Raspberry Pi, eigener Platine und selbstgebauter Fernbedienung – inklusive Hinderniserkennung und zwei Live-Kameras. Auf dieser Demo-Seite steigst du selbst ein: virtueller Joystick, Kamerabilder und alle Sensordaten live aus dem Auto.',
    status: {                       // kleine Anzeigen unter der Einleitung
      server: 'Server',
      auto: 'Auto',
      fahrmodus: 'Fahrmodus',
      pakete: 'Pakete/s',
    },
  },

  steuerung: {
    titel: 'Steuerung',
    achseX: 'X',
    achseY: 'Y',
    rohwerte: 'Rohwerte 0 bis 4095, Mitte = 2048 – 12 Bit wie der echte Joystick',
    tippHandy: 'Tipp: Handy quer halten, dann siehst du beide Kameras und alle Werte beim Fahren.',
    joystickBeschreibung: 'Virtueller Joystick',          // für Screenreader
    vollbild: {
      an: 'Vollbild und Querformat',                       // Text des Knopfs
      aus: 'Vollbild beenden',
    },
    meldungen: {
      bereit: 'Knauf ziehen oder mit Pfeiltasten und WASD fahren.',
      keinSchluessel: 'Nur Ansicht: Der Zugangsschlüssel fehlt oder ist nicht mehr gültig. Bitte den QR-Code erneut scannen.',
      gesperrt: 'Die Verbindung zum Auto ist derzeit vom Admin gesperrt.',
      autoGetrennt: 'Das Auto ist nicht verbunden. Der Server versucht es weiter.',
      vollbildAbgelehnt: 'Der Browser hat das Vollbild abgelehnt.',
      vollbildNichtMoeglich: 'Dieser Browser erlaubt kein Vollbild. Tipp: Seite zum Home-Bildschirm hinzufügen, dann öffnet sie ohne Adressleiste.',
      handyDrehen: 'Bitte das Handy quer drehen.',
    },
  },

  kameras: {
    titel: 'Blick aus Natascha',
    einleitung: 'Zwei Kameras an Bord zeigen live, was vor und hinter dem Auto passiert – direkt vom Auto auf diese Seite.',
    vorne: 'Vorne',
    hinten: 'Hinten',
    bildVorne: 'Livebild der Frontkamera',                 // für Screenreader
    bildHinten: 'Livebild der Rückkamera',
    meldungen: {                                           // statt des Bildes
      verbinde: 'Verbinde …',
      adminAus: 'Kamera vom Admin deaktiviert',
      nurMitSchluessel: 'Kamerabild nur mit Zugangsschlüssel',
      wartenAufBild: 'Warte auf Bild …',
      keineVerbindung: 'Keine Verbindung zum Server',
    },
  },

  telemetrie: {
    titel: 'Live vom Auto',
    einleitung: 'Captain, der Raspberry Pi im Auto, liest Akku, Stromaufnahme, Lenkwinkel und die Time-of-Flight-Abstände vorne und hinten aus und schickt sie per TCP an diese Seite. Der Abstand wird rot, sobald ein Hindernis näher als 50 cm ist.',
    akku: 'Akku',
    strom: 'Stromaufnahme',
    lenkung: 'Lenkung',
    abstand: 'Abstand zu Hindernissen',
    einheitSpannung: 'V',
    einheitStrom: 'A',
    einheitAbstandVorne: 'm vorne',
    einheitAbstandHinten: 'm hinten',
    leer: '–',                                             // wenn kein Wert da ist
  },

  technik: {
    titel: 'So kommt dein Daumen ans Auto',
    einleitung: 'Browser können keine UDP- oder TCP-Verbindungen öffnen. Deshalb vermittelt bei dieser Demo ein Server zwischen Website und Auto – im echten Betrieb macht das die selbstgebaute Fernbedienung „Control“ direkt über WLAN.',
    schritte: [                                            // beliebig viele, die Nummern kommen automatisch
      { titel: 'Joystick', text: 'Der Browser rechnet die Knauf-Position in X und Y von 0 bis 4095 um – 12 Bit, genau wie der Analogstick der echten Fernbedienung am MCP3204-ADC.' },
      { titel: 'WebSocket', text: 'Die Werte gehen etwa 30-mal pro Sekunde an den Demo-Server.' },
      { titel: 'UDP und TCP', text: 'Der Server sendet die Joystickdaten per UDP (Port 9005) an Natascha und empfängt die Sensordaten per TCP (Port 9006) – derselbe Weg, den auch „Control“ zu „Captain“ nutzt.' },
      { titel: 'Captain im Auto', text: 'Der Raspberry Pi im Auto wertet alles in eigenen Threads aus und steuert Motor und Lenkung. Kommen keine Steuerdaten mehr an, stoppt er die Motoren.' },
      { titel: 'Control', text: 'Die handliche Fernbedienung – ESP32, Joystick, LCD, Buzzer, 3D-gedruckte Hülle für unter 20 € – steuert Natascha alternativ direkt im WLAN, mit den Modi Manuell, Halb-Automatik, Automatik und Info.' },
    ],
    live: {
      titel: 'Live: so verarbeitet das Auto dein Input',
      pakete: 'Pakete',
      browser: 'Browser',
      server: 'Demo-Server',
      captain: 'Captain im Auto',
      antrieb: 'Motor & Lenkung',
      ws: 'WebSocket',
      udp: 'UDP 9005',
      intern: 'Threads',
      tip: 'Zieh den Joystick oben – jeder blaue Punkt ist ein gesendetes Steuerpaket auf dem Weg zum Auto.',
    },
  },

  projekt: {
    titel: 'Das Projekt hinter Natascha',
    einleitung: 'Natascha entstand als P5-Projektarbeit (Abitur 2027) in den Fächern TPR/ENG: Im Frühjahr 2026 haben wir ein vorhandenes Kinderauto zum Fahrroboter umgebaut – mit eigener Platine, Raspberry Pi als Bordcomputer „Captain“, selbstgebauter ESP32-Fernbedienung „Control“, diesem Webinterface und einer lasercut-gefertigten Holzkiste als Gewichtsfach im Heck.',
    eckdaten: [                                            // [Bezeichnung, Wert], beliebig viele
      ['Anlass', 'P5-Projektarbeit (Abitur 2027), Fächer TPR/ENG'],
      ['Zeitraum', 'Februar bis Juni 2026'],
      ['Basisfahrzeug', 'Kinderauto – eigentlich zum Mitfahren gedacht'],
      ['Bordcomputer „Captain“', 'Raspberry Pi mit Python und Threading'],
      ['Fernbedienung „Control“', 'ESP32, Analog-Joystick, LCD, Buzzer – unter 20 €'],
      ['Platine', 'Eigenes KiCad-Layout: MCP3204-ADC (12 Bit), Schraubklemmen, bei JLCPCB bestellt'],
      ['Sensorik', 'Time-of-Flight-Abstand vorne/hinten, Akku-Spannung, Strom, Lenkwinkel'],
      ['Kameras', 'Zwei Stück – Livebild vorne und hinten'],
      ['Übertragung', 'WLAN: UDP Port 9005 für die Steuerung, TCP Port 9006 für Sensordaten'],
      ['Sicherheit', 'Watchdog: ohne Datenstrom stoppen die Motoren'],
      ['Design', 'Lasercut-Holzkiste im Heck mit ca. 5 kg Gewicht gegen Rutschen (Hartplastik-Reifen)'],
      ['Quellcode', 'GitHub-Organisation „P5-Natascha“: Captain, Control, Interface, Guidance, DemoInterface'],
    ],
  },

  fusszeile: {
    sicherheit: 'Sicherheit: Kommt länger als eine halbe Sekunde kein Steuersignal an, stoppt das Auto die Motoren.',
    datenschutz: 'Datenschutz: Diese Seite speichert keine personenbezogenen Daten.',
    githubKnopf: 'Quellcode auf GitHub',
  },
};
