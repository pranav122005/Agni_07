import Felgo
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

App {
    id: app
    licenseKey: "your_felgo_license_key_here"

    // ─── THEME COLORS ─────────────────────────────────────────────────────────
    readonly property color bgDeep:        "#0A0F1E"
    readonly property color bgPanel:       "#0D1529"
    readonly property color bgCard:        "#111D35"
    readonly property color accentAmber:   "#F5A623"
    readonly property color accentRed:     "#E84545"
    readonly property color accentTeal:    "#00D4AA"
    readonly property color accentBlue:    "#4A9EFF"
    readonly property color textPrimary:   "#E8EDF5"
    readonly property color textSecondary: "#7B8BAE"
    readonly property color textMuted:     "#3D4F6E"
    readonly property color borderColor:   "#1E2D4A"
    readonly property color borderActive:  "#2A4080"

    // ─── GROQ CONFIG ──────────────────────────────────────────────────────────
    readonly property string groqApiKey:   "YOUR_GROQ_API_KEY_HERE"
    readonly property string groqModel:    "llama-3.3-70b-versatile"
    readonly property string systemPrompt: "You are RAAM — Road Assistance & Alert Monitor. You are an AI co-pilot designed to assist drivers during emergencies, stressful situations, or when they need guidance on the road.\n\nYour personality:\n- Calm, warm, and reassuring at all times\n- Speak in a natural, conversational tone — like a trusted friend in the passenger seat\n- Use simple, clear language — no jargon\n- Be concise but thorough — drivers need quick answers\n- Always prioritize safety first\n- Acknowledge emotions — if someone is scared or stressed, validate that first\n\nYour capabilities:\n- Guide drivers through emergency situations (accidents, breakdowns, medical emergencies)\n- Provide step-by-step instructions for common roadside problems\n- Help navigate stressful driving situations\n- Offer calming reassurance during anxiety-inducing situations\n- Advise when to call emergency services (911)\n\nAlways start with the most critical safety information. Keep responses short when urgency is high. Use gentle, supportive language. Never panic — your calm is contagious."

    // ─── STATE ────────────────────────────────────────────────────────────────
    property var conversationHistory: []
    property bool isThinking: false
    property string statusText: "ACTIVE"
    property color statusColor: accentTeal
    property string currentStreamedText: ""

    // ─── NETWORKING ───────────────────────────────────────────────────────────
    property var activeRequest: null

    function sendToGroq(userMessage) {
        if (isThinking) return

        // Build messages array
        var messages = [{ role: "system", content: systemPrompt }]
        for (var i = 0; i < conversationHistory.length; i++) {
            messages.push(conversationHistory[i])
        }
        messages.push({ role: "user", content: userMessage })

        // Add user bubble
        addMessage(userMessage, true)
        conversationHistory.push({ role: "user", content: userMessage })

        isThinking = true
        statusText = "THINKING"
        statusColor = accentAmber
        currentStreamedText = ""

        // Create XHR request
        var xhr = new XMLHttpRequest()
        activeRequest = xhr

        xhr.open("POST", "https://api.groq.com/openai/v1/chat/completions")
        xhr.setRequestHeader("Content-Type", "application/json")
        xhr.setRequestHeader("Authorization", "Bearer " + groqApiKey)

        var payload = JSON.stringify({
            model: groqModel,
            messages: messages,
            temperature: 0.7,
            max_tokens: 500,
            stream: false
        })

        xhr.onreadystatechange = function() {
            if (xhr.readyState === XMLHttpRequest.DONE) {
                if (xhr.status === 200) {
                    try {
                        var data = JSON.parse(xhr.responseText)
                        var reply = data.choices[0].message.content
                        addMessage(reply, false)
                        conversationHistory.push({ role: "assistant", content: reply })
                    } catch(e) {
                        addMessage("I encountered an error parsing the response. If this is an emergency, please call 911 immediately.", false)
                    }
                } else {
                    var errMsg = "I'm having trouble connecting right now. If this is an emergency, please call 911 immediately."
                    try {
                        var errData = JSON.parse(xhr.responseText)
                        if (errData.error) errMsg += " (" + errData.error.message + ")"
                    } catch(e) {}
                    addMessage(errMsg, false)
                }
                isThinking = false
                statusText = "ACTIVE"
                statusColor = accentTeal
                activeRequest = null
            }
        }

        xhr.send(payload)
    }

    function addMessage(text, isUser) {
        messagesModel.append({ text: text, isUser: isUser })
        // Scroll to bottom after brief delay
        scrollTimer.restart()
    }

    function clearChat() {
        messagesModel.clear()
        conversationHistory = []
        Qt.callLater(sendWelcome)
    }

    function sendWelcome() {
        var welcome = "Hello! I'm RAAM, your Road Assistance & Alert Monitor. I'm here with you, calm and ready to help. Whether it's a breakdown, an accident, or just a stressful drive — tell me what's happening and we'll handle it together. 🧡"
        addMessage(welcome, false)
    }

    Component.onCompleted: {
        Qt.callLater(sendWelcome)
    }

    Timer {
        id: scrollTimer
        interval: 80
        onTriggered: messageListView.positionViewAtEnd()
    }

    ListModel { id: messagesModel }

    // ─── ROOT PAGE ────────────────────────────────────────────────────────────
    NavigationStack {
        Page {
            id: mainPage
            backgroundColor: app.bgDeep
            title: ""
            navigationBarHidden: true

            Rectangle {
                anchors.fill: parent
                color: app.bgDeep

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    // ── TOP STATUS BAR ─────────────────────────────────────────
                    Rectangle {
                        Layout.fillWidth: true
                        height: dp(52)
                        color: app.bgPanel

                        Rectangle {
                            anchors.bottom: parent.bottom
                            width: parent.width
                            height: 1
                            color: app.borderColor
                        }

                        RowLayout {
                            anchors { fill: parent; leftMargin: dp(20); rightMargin: dp(20) }
                            spacing: dp(12)

                            AppText {
                                text: "◈ RAAM"
                                font.pixelSize: sp(15)
                                font.bold: true
                                color: app.accentAmber
                                font.letterSpacing: 3
                            }

                            AppText {
                                id: statusIndicator
                                text: "● " + app.statusText
                                font.pixelSize: sp(10)
                                color: app.statusColor

                                Behavior on color { ColorAnimation { duration: 300 } }
                            }

                            Item { Layout.fillWidth: true }

                            Rectangle {
                                width: aiBadgeText.implicitWidth + dp(16)
                                height: dp(22)
                                color: "transparent"
                                border.color: Qt.rgba(245/255, 166/255, 35/255, 0.3)
                                border.width: 1
                                radius: dp(4)

                                AppText {
                                    id: aiBadgeText
                                    anchors.centerIn: parent
                                    text: "AI COPILOT"
                                    font.pixelSize: sp(8)
                                    font.bold: true
                                    color: app.accentAmber
                                    font.letterSpacing: 2
                                }
                            }

                            AppText {
                                id: clockLabel
                                font.pixelSize: sp(10)
                                color: app.textSecondary

                                Timer {
                                    interval: 1000
                                    running: true
                                    repeat: true
                                    onTriggered: clockLabel.text = Qt.formatDateTime(new Date(), "hh:mm  dd MMM yyyy")
                                    Component.onCompleted: triggered()
                                }
                            }
                        }
                    }

                    // ── MAIN BODY ──────────────────────────────────────────────
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        spacing: 0

                        // ── LEFT SIDEBAR ───────────────────────────────────────
                        Rectangle {
                            width: dp(210)
                            Layout.fillHeight: true
                            color: app.bgPanel

                            Rectangle {
                                anchors.right: parent.right
                                width: 1
                                height: parent.height
                                color: app.borderColor
                            }

                            ColumnLayout {
                                anchors { fill: parent; margins: dp(16) }
                                spacing: dp(10)

                                // Pulse + title
                                RowLayout {
                                    spacing: dp(10)

                                    // Pulse dot
                                    Item {
                                        width: dp(40)
                                        height: dp(40)

                                        Rectangle {
                                            id: pulseOuter
                                            anchors.centerIn: parent
                                            width: dp(32)
                                            height: dp(32)
                                            radius: width / 2
                                            color: Qt.rgba(0, 212/255, 170/255, 0.15)

                                            SequentialAnimation on width {
                                                loops: Animation.Infinite
                                                NumberAnimation { to: dp(38); duration: 900; easing.type: Easing.InOutSine }
                                                NumberAnimation { to: dp(26); duration: 900; easing.type: Easing.InOutSine }
                                            }
                                            onWidthChanged: height = width; radius = width/2
                                        }

                                        Rectangle {
                                            anchors.centerIn: parent
                                            width: dp(14)
                                            height: dp(14)
                                            radius: width / 2
                                            color: app.accentTeal
                                        }
                                    }

                                    ColumnLayout {
                                        spacing: 2
                                        AppText {
                                            text: "RAAM"
                                            font.pixelSize: sp(13)
                                            font.bold: true
                                            color: app.textPrimary
                                        }
                                        AppText {
                                            text: "Active"
                                            font.pixelSize: sp(10)
                                            color: app.accentTeal
                                        }
                                    }
                                }

                                // Divider
                                Rectangle { Layout.fillWidth: true; height: 1; color: app.borderColor }

                                AppText {
                                    text: "QUICK SCENARIOS"
                                    font.pixelSize: sp(8)
                                    font.bold: true
                                    color: app.textMuted
                                    font.letterSpacing: 2
                                }

                                // Scenario buttons
                                Repeater {
                                    model: [
                                        { icon: "🚨", label: "Emergency SOS",  msg: "I need immediate help — emergency!" },
                                        { icon: "💥", label: "Accident",        msg: "I've been in a car accident." },
                                        { icon: "🔧", label: "Breakdown",       msg: "My car broke down on the road." },
                                        { icon: "🩺", label: "Medical",         msg: "I'm feeling unwell while driving." },
                                        { icon: "🌧️", label: "Bad Weather",     msg: "Weather conditions are dangerous." },
                                        { icon: "⛽", label: "Out of Fuel",     msg: "I've run out of fuel." },
                                        { icon: "🔒", label: "Locked Out",      msg: "I'm locked out of my car." },
                                        { icon: "🛞", label: "Flat Tire",       msg: "I have a flat tire." }
                                    ]

                                    delegate: Rectangle {
                                        Layout.fillWidth: true
                                        height: dp(34)
                                        color: scenarioHover.containsMouse ? Qt.rgba(245/255,166/255,35/255, 0.08) : Qt.rgba(1,1,1,0.03)
                                        border.color: scenarioHover.containsMouse ? Qt.rgba(245/255,166/255,35/255, 0.3) : app.borderColor
                                        border.width: 1
                                        radius: dp(8)

                                        RowLayout {
                                            anchors { fill: parent; leftMargin: dp(8); rightMargin: dp(8) }
                                            spacing: dp(6)
                                            AppText {
                                                text: modelData.icon
                                                font.pixelSize: sp(13)
                                            }
                                            AppText {
                                                text: modelData.label
                                                font.pixelSize: sp(9)
                                                color: scenarioHover.containsMouse ? app.accentAmber : app.textSecondary
                                                Layout.fillWidth: true
                                                elide: Text.ElideRight
                                            }
                                        }

                                        HoverHandler { id: scenarioHover }
                                        TapHandler {
                                            onTapped: {
                                                if (!app.isThinking) {
                                                    app.sendToGroq(modelData.msg)
                                                }
                                            }
                                        }
                                        Behavior on color { ColorAnimation { duration: 150 } }
                                    }
                                }

                                Item { Layout.fillHeight: true }

                                // TTS Toggle (decorative — real TTS needs native plugin)
                                Rectangle {
                                    Layout.fillWidth: true
                                    height: dp(36)
                                    color: Qt.rgba(0, 212/255, 170/255, 0.1)
                                    border.color: Qt.rgba(0, 212/255, 170/255, 0.3)
                                    border.width: 1
                                    radius: dp(8)

                                    AppText {
                                        anchors.centerIn: parent
                                        text: "🔊  Voice Ready"
                                        font.pixelSize: sp(9)
                                        color: app.accentTeal
                                    }
                                }

                                // Clear Chat
                                Rectangle {
                                    Layout.fillWidth: true
                                    height: dp(36)
                                    color: clearHover.containsMouse ? Qt.rgba(1,1,1,0.08) : Qt.rgba(1,1,1,0.04)
                                    border.color: app.borderColor
                                    border.width: 1
                                    radius: dp(8)

                                    AppText {
                                        anchors.centerIn: parent
                                        text: "🗑  Clear Chat"
                                        font.pixelSize: sp(9)
                                        color: app.textSecondary
                                    }

                                    HoverHandler { id: clearHover }
                                    TapHandler { onTapped: app.clearChat() }
                                    Behavior on color { ColorAnimation { duration: 150 } }
                                }
                            }
                        }

                        // ── CHAT AREA ──────────────────────────────────────────
                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            spacing: 0

                            // Chat header
                            Rectangle {
                                Layout.fillWidth: true
                                height: dp(52)
                                color: app.bgCard

                                Rectangle {
                                    anchors.bottom: parent.bottom
                                    width: parent.width
                                    height: 1
                                    color: app.borderColor
                                }

                                RowLayout {
                                    anchors { fill: parent; leftMargin: dp(24); rightMargin: dp(24) }

                                    AppText {
                                        text: "RAAM Assistant"
                                        font.pixelSize: sp(13)
                                        font.bold: true
                                        color: app.textPrimary
                                    }

                                    AppText {
                                        text: app.isThinking ? "RAAM is thinking..." : ""
                                        font.pixelSize: sp(10)
                                        color: app.accentTeal

                                        SequentialAnimation on opacity {
                                            loops: Animation.Infinite
                                            running: app.isThinking
                                            NumberAnimation { to: 0.3; duration: 600 }
                                            NumberAnimation { to: 1.0; duration: 600 }
                                        }
                                    }

                                    Item { Layout.fillWidth: true }

                                    AppText {
                                        text: app.groqApiKey === "YOUR_GROQ_API_KEY_HERE" ? "⚠ Add API Key" : "✓ Groq Connected"
                                        font.pixelSize: sp(9)
                                        color: app.groqApiKey === "YOUR_GROQ_API_KEY_HERE" ? app.accentAmber : app.accentTeal
                                    }
                                }
                            }

                            // Messages list
                            ListView {
                                id: messageListView
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                model: messagesModel
                                spacing: dp(8)
                                clip: true
                                topMargin: dp(16)
                                bottomMargin: dp(16)
                                leftMargin: dp(16)
                                rightMargin: dp(16)

                                ScrollBar.vertical: ScrollBar {
                                    policy: ScrollBar.AsNeeded
                                    contentItem: Rectangle {
                                        implicitWidth: dp(5)
                                        radius: dp(3)
                                        color: app.borderActive
                                    }
                                }

                                delegate: Item {
                                    width: messageListView.width - dp(32)
                                    height: bubbleRow.implicitHeight + dp(4)

                                    RowLayout {
                                        id: bubbleRow
                                        width: parent.width
                                        spacing: 0

                                        Item {
                                            Layout.fillWidth: !model.isUser
                                            visible: !model.isUser
                                        }

                                        Rectangle {
                                            Layout.maximumWidth: parent.width * 0.75
                                            width: Math.min(bubbleText.implicitWidth + dp(28), parent.width * 0.75)
                                            height: bubbleText.implicitHeight + dp(20)

                                            color: model.isUser
                                                   ? Qt.rgba(74/255, 158/255, 255/255, 0.15)
                                                   : Qt.rgba(0, 212/255, 170/255, 0.08)

                                            border.color: model.isUser
                                                          ? Qt.rgba(74/255, 158/255, 255/255, 0.3)
                                                          : Qt.rgba(0, 212/255, 170/255, 0.2)
                                            border.width: 1

                                            radius: model.isUser ? dp(16) : dp(16)

                                            AppText {
                                                id: bubbleText
                                                anchors {
                                                    left: parent.left
                                                    right: parent.right
                                                    verticalCenter: parent.verticalCenter
                                                    leftMargin: dp(14)
                                                    rightMargin: dp(14)
                                                }
                                                text: model.text
                                                wrapMode: Text.WordWrap
                                                font.pixelSize: sp(11)
                                                color: app.textPrimary
                                            }
                                        }

                                        Item {
                                            Layout.fillWidth: model.isUser
                                            visible: model.isUser
                                        }
                                    }
                                }
                            }

                            // Typing indicator
                            Rectangle {
                                Layout.fillWidth: true
                                height: app.isThinking ? dp(36) : 0
                                visible: app.isThinking
                                color: app.bgDeep

                                Behavior on height { NumberAnimation { duration: 200 } }

                                RowLayout {
                                    anchors { left: parent.left; leftMargin: dp(24); verticalCenter: parent.verticalCenter }
                                    spacing: dp(5)

                                    Repeater {
                                        model: 3
                                        Rectangle {
                                            width: dp(8); height: dp(8)
                                            radius: width/2
                                            color: app.accentTeal
                                            opacity: 0.4

                                            SequentialAnimation on opacity {
                                                loops: Animation.Infinite
                                                running: app.isThinking
                                                PauseAnimation { duration: index * 200 }
                                                NumberAnimation { to: 1.0; duration: 400 }
                                                NumberAnimation { to: 0.4; duration: 400 }
                                            }
                                        }
                                    }

                                    AppText {
                                        text: "RAAM is responding..."
                                        font.pixelSize: sp(10)
                                        color: app.textMuted
                                        leftPadding: dp(6)
                                    }
                                }
                            }

                            // ── INPUT AREA ─────────────────────────────────────
                            Rectangle {
                                Layout.fillWidth: true
                                height: dp(76)
                                color: app.bgPanel

                                Rectangle {
                                    anchors.top: parent.top
                                    width: parent.width
                                    height: 1
                                    color: app.borderColor
                                }

                                RowLayout {
                                    anchors { fill: parent; leftMargin: dp(20); rightMargin: dp(20); topMargin: dp(14); bottomMargin: dp(14) }
                                    spacing: dp(12)

                                    Rectangle {
                                        Layout.fillWidth: true
                                        height: dp(46)
                                        color: app.bgCard
                                        border.color: inputField.activeFocus ? app.accentAmber : app.borderColor
                                        border.width: 1
                                        radius: dp(12)

                                        Behavior on border.color { ColorAnimation { duration: 200 } }

                                        TextField {
                                            id: inputField
                                            anchors { fill: parent; leftMargin: dp(16); rightMargin: dp(16) }
                                            placeholderText: "Describe your situation... RAAM is here to help"
                                            font.pixelSize: sp(12)
                                            color: app.textPrimary
                                            background: Item {}
                                            enabled: !app.isThinking
                                            selectionColor: Qt.rgba(245/255, 166/255, 35/255, 0.4)

                                            Keys.onReturnPressed: sendMessage()
                                            Keys.onEnterPressed: sendMessage()

                                            placeholderTextColor: app.textMuted
                                        }
                                    }

                                    Rectangle {
                                        width: dp(100)
                                        height: dp(46)
                                        color: sendHover.containsMouse
                                               ? "#F7BC50"
                                               : app.isThinking ? app.textMuted : app.accentAmber
                                        radius: dp(12)
                                        opacity: app.isThinking ? 0.5 : 1.0

                                        Behavior on color { ColorAnimation { duration: 150 } }

                                        AppText {
                                            anchors.centerIn: parent
                                            text: "Send ↗"
                                            font.pixelSize: sp(11)
                                            font.bold: true
                                            color: "#0A0F1E"
                                        }

                                        HoverHandler { id: sendHover }
                                        TapHandler {
                                            onTapped: sendMessage()
                                        }
                                    }
                                }
                            }
                        }

                        // ── RIGHT PANEL ────────────────────────────────────────
                        Rectangle {
                            width: dp(230)
                            Layout.fillHeight: true
                            color: app.bgPanel

                            Rectangle {
                                anchors.left: parent.left
                                width: 1
                                height: parent.height
                                color: app.borderColor
                            }

                            ColumnLayout {
                                anchors { fill: parent; margins: dp(16) }
                                spacing: dp(10)

                                AppText {
                                    text: "EMERGENCY CONTACTS"
                                    font.pixelSize: sp(8)
                                    font.bold: true
                                    color: app.textMuted
                                    font.letterSpacing: 2
                                }

                                Repeater {
                                    model: [
                                        { icon: "🚑", name: "Ambulance",      number: "911" },
                                        { icon: "🚒", name: "Fire Dept",      number: "911" },
                                        { icon: "🚔", name: "Police",         number: "911" },
                                        { icon: "🛣️", name: "Road Help",      number: "1-800-AAA" },
                                        { icon: "💊", name: "Poison Control", number: "1-800-222-1222" }
                                    ]

                                    delegate: Rectangle {
                                        Layout.fillWidth: true
                                        height: dp(40)
                                        color: Qt.rgba(1,1,1,0.03)
                                        border.color: app.borderColor
                                        border.width: 1
                                        radius: dp(8)

                                        RowLayout {
                                            anchors { fill: parent; leftMargin: dp(10); rightMargin: dp(10) }
                                            spacing: dp(6)

                                            AppText { text: modelData.icon; font.pixelSize: sp(14) }

                                            AppText {
                                                text: modelData.name
                                                font.pixelSize: sp(9)
                                                color: app.textSecondary
                                                Layout.fillWidth: true
                                                elide: Text.ElideRight
                                            }

                                            AppText {
                                                text: modelData.number
                                                font.pixelSize: sp(9)
                                                font.bold: true
                                                color: app.accentTeal
                                            }
                                        }
                                    }
                                }

                                Rectangle { Layout.fillWidth: true; height: 1; color: app.borderColor }

                                AppText {
                                    text: "SAFETY REMINDERS"
                                    font.pixelSize: sp(8)
                                    font.bold: true
                                    color: app.textMuted
                                    font.letterSpacing: 2
                                }

                                Repeater {
                                    model: [
                                        "Stay in your vehicle if safe",
                                        "Turn on hazard lights",
                                        "Move to shoulder if possible",
                                        "Keep calm & breathe slowly",
                                        "Stay on the line with 911"
                                    ]

                                    delegate: AppText {
                                        text: "· " + modelData
                                        font.pixelSize: sp(9)
                                        color: app.textSecondary
                                        wrapMode: Text.WordWrap
                                        Layout.fillWidth: true
                                    }
                                }

                                Item { Layout.fillHeight: true }

                                // SOS Button
                                Rectangle {
                                    Layout.fillWidth: true
                                    height: dp(52)
                                    color: sosHover.containsMouse
                                           ? Qt.rgba(232/255, 69/255, 69/255, 0.25)
                                           : Qt.rgba(232/255, 69/255, 69/255, 0.15)
                                    border.color: app.accentRed
                                    border.width: 2
                                    radius: dp(12)

                                    Behavior on color { ColorAnimation { duration: 150 } }

                                    RowLayout {
                                        anchors.centerIn: parent
                                        spacing: dp(8)
                                        AppText {
                                            text: "🆘"
                                            font.pixelSize: sp(16)
                                        }
                                        AppText {
                                            text: "SOS EMERGENCY"
                                            font.pixelSize: sp(11)
                                            font.bold: true
                                            color: app.accentRed
                                            font.letterSpacing: 1
                                        }
                                    }

                                    HoverHandler { id: sosHover }
                                    TapHandler {
                                        onTapped: {
                                            if (!app.isThinking)
                                                app.sendToGroq("EMERGENCY! I need immediate help right now!")
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // ─── HELPER ───────────────────────────────────────────────────────────────
    function sendMessage() {
        var text = inputField.text.trim()
        if (!text || app.isThinking) return
        inputField.text = ""
        app.sendToGroq(text)
    }
}
