/* Sanctum OS — Calamares install slideshow (slideshowAPI 2). */
import QtQuick 2.0;
import calamares.slideshow 1.0;

Presentation
{
    id: presentation

    Timer {
        id: advanceTimer
        interval: 9000
        running: presentation.activatedInCalamares
        repeat: true
        onTriggered: presentation.goToNextSlide()
    }

    function onActivate() { presentation.currentSlide = 0; }
    function onLeave() { advanceTimer.running = false; }

    // Shared canvas
    Rectangle { anchors.fill: parent; color: "#F7F6F3"; z: -1 }

    Slide {
        anchors.fill: parent
        Column {
            anchors.centerIn: parent
            spacing: 18
            Image {
                source: "logo.png"
                width: 96; height: 96
                anchors.horizontalCenter: parent.horizontalCenter
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "A protected place for serious work."
                font.family: "Inter"; font.pixelSize: 30; font.weight: Font.Light
                color: "#1A1A1E"
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Sanctum OS is being placed on your disk."
                font.family: "Inter"; font.pixelSize: 16
                color: "#6E6E76"
            }
        }
    }

    Slide {
        anchors.fill: parent
        Column {
            anchors.centerIn: parent
            spacing: 14
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Secure by default"
                font.family: "Inter"; font.pixelSize: 28; font.weight: Font.Light
                color: "#1A1A1E"
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                horizontalAlignment: Text.AlignHCenter
                text: "Firewall closed to the world.  Disk fully encrypted.\nApplications sandboxed.  Security updates apply themselves.\nEncrypted DNS through Quad9.  Nothing phones home."
                font.family: "Inter"; font.pixelSize: 16; lineHeight: 1.4
                color: "#6E6E76"
            }
        }
    }

    Slide {
        anchors.fill: parent
        Column {
            anchors.centerIn: parent
            spacing: 14
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Only what you need"
                font.family: "Inter"; font.pixelSize: 28; font.weight: Font.Light
                color: "#1A1A1E"
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                horizontalAlignment: Text.AlignHCenter
                text: "Claude Desktop for AI work.  Firefox for the web.\nTelegram for people.  A terminal and Settings.\nThat is the whole system — nothing else to distrust."
                font.family: "Inter"; font.pixelSize: 16; lineHeight: 1.4
                color: "#6E6E76"
            }
        }
    }
}
