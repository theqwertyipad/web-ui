(function (recording = false) {
  const fontFamily = "'Segoe UI', Roboto, Helvetica, Arial, sans-serif";
  const overlay = document.createElement('div');
  overlay.id = 'agent-recorder-ui';

  Object.assign(overlay.style, {
    position: 'fixed',
    top: '100px',
    right: '30px',
    width: '300px',
    background: '#1a1a1a',
    color: '#fff',
    padding: '16px',
    borderRadius: '12px',
    zIndex: 2147483647,
    fontFamily: fontFamily,
    fontSize: '15px',
    boxShadow: '0 8px 24px rgba(0,0,0,0.3)',
    userSelect: 'none',
  });

  const header = document.createElement('div');
  header.id = 'drag-header';
  header.style.display = 'flex';
  header.style.justifyContent = 'space-between';
  header.style.alignItems = 'center';
  header.style.fontWeight = 'bold';
  header.style.marginBottom = '12px';
  header.style.paddingBottom = '6px';
  header.style.borderBottom = '1px solid #444';
  header.style.fontSize = '16px';

  const title = document.createElement('span');
  title.innerText = 'Workflow Recorder';
  const sidePanel = document.createElement('div');
  sidePanel.id = 'workflow-history';
  Object.assign(sidePanel.style, {
    position: 'fixed',
    top: '100px',
    right: '450px', // Adjusted to account for wider main panel (400px + padding)
    width: '250px',
    background: '#161616',
    color: '#fff',
    padding: '16px',
    borderRadius: '12px',
    zIndex: 2147483646,
    fontFamily: fontFamily,
    fontSize: '14px',
    boxShadow: '0 8px 24px rgba(0,0,0,0.3)',
    overflowY: 'auto',
    maxHeight: '80vh',
  });

  const historyTitle = document.createElement('div');
  historyTitle.innerText = '🧠 Workflow History';
  historyTitle.style.fontWeight = 'bold';
  historyTitle.style.marginBottom = '12px';

  const historyList = document.createElement('div');
  historyList.id = 'workflow-steps';
  historyList.style.display = 'flex';
  historyList.style.flexDirection = 'column';
  historyList.style.gap = '20px';

  sidePanel.appendChild(historyTitle);
  const backButton = document.createElement('button');
  backButton.innerText = 'Undo Last Step';
  Object.assign(backButton.style, {
    marginBottom: '12px',
    background: '#444',
    color: '#fff',
    padding: '6px 12px',
    border: 'none',
    borderRadius: '6px',
    cursor: 'pointer',
    fontSize: '14px',
  });
  backButton.onclick = () => {
    const lastStep = historyList.lastElementChild;
    if (lastStep) {
      historyList.removeChild(lastStep);
      window.notifyPython?.('control', { action: 'back' });
    }
  };
  sidePanel.appendChild(backButton);
  sidePanel.appendChild(historyList);
  overlay.appendChild(sidePanel);

  const toggleBtn = document.createElement('button');
  toggleBtn.id = 'toggle-record-btn';
  toggleBtn.innerText = recording ? 'Stop' : 'Start';
  Object.assign(toggleBtn.style, {
    background: recording ? '#e53935' : '#4CAF50',
    color: 'white',
    padding: '3px 8px',
    border: 'none',
    borderRadius: '6px',
    cursor: 'pointer',
    display: 'inline-block',
  });

  header.appendChild(title);

  // Button group container
  const headerButtons = document.createElement('div');
  headerButtons.style.display = 'flex';
  headerButtons.style.gap = '6px';

  // History button
  const toggleHistoryBtn = document.createElement('button');
  toggleHistoryBtn.innerText = '🧠';
  toggleHistoryBtn.title = 'Toggle Workflow History';
  Object.assign(toggleHistoryBtn.style, {
    background: '#3a3a3a',
    color: 'white',
    padding: '3px 6px',
    border: 'none',
    borderRadius: '6px',
    cursor: 'pointer',
    fontSize: '16px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    minWidth: '32px',
  });

  toggleHistoryBtn.onclick = () => {
    const isVisible = sidePanel.style.display !== 'none';
    sidePanel.style.display = isVisible ? 'none' : 'block';
    if (!isVisible) {
      const rect = overlay.getBoundingClientRect();
      sidePanel.style.top = `${rect.top}px`;
      sidePanel.style.left = `${rect.left - sidePanel.offsetWidth - 20}px`;
      sidePanel.style.right = 'auto';
    }
  };

  // Stop button
  Object.assign(toggleBtn.style, {
    background: '#e53935',
    color: 'white',
    padding: '4px 12px',
    border: 'none',
    borderRadius: '6px',
    cursor: 'pointer',
    fontWeight: 'bold',
    fontSize: '14px',
    display: 'none',
  });

  headerButtons.appendChild(toggleHistoryBtn);
  headerButtons.appendChild(toggleBtn);
  header.appendChild(headerButtons);
  sidePanel.style.display = 'none';
  overlay.appendChild(header);

  const recorderContent = document.createElement('div');
  recorderContent.id = 'recorder-content';
  recorderContent.style.display = 'flex';
  recorderContent.style.gap = '10px';

  const mainContent = document.createElement('div');
  mainContent.style.flex = '1';

  const outputBox = document.createElement('div');
  outputBox.id = 'output-box';
  Object.assign(outputBox.style, {
    marginTop: '10px',
    background: '#1d1d1d',
    padding: '8px',
    borderRadius: '6px',
    minHeight: '80px',
    fontFamily: fontFamily,
    fontSize: '13px',
    overflowY: 'auto',
    overflowX: 'auto',
    maxHeight: '120px',
    boxSizing: 'border-box',
    whiteSpace: 'normal',
    wordBreak: 'break-word',
    width: '100%',
    display: 'flex',
    flexDirection: 'column',
    gap: '0',
  });
  mainContent.appendChild(outputBox);

  const inputContainer = document.createElement('div');
  inputContainer.id = 'input-container';
  inputContainer.style.marginTop = '16px';
  inputContainer.style.display = 'none';

  const inputLabel = document.createElement('label');
  inputLabel.id = 'input-label';
  inputLabel.style.fontWeight = '600';
  inputLabel.style.marginBottom = '4px';
  inputLabel.style.display = 'block';

  const inputBox = document.createElement('div');
  inputBox.id = 'input-box';
  Object.assign(inputBox.style, {
    maxHeight: '200px',
    overflowY: 'auto',
  });

  inputContainer.appendChild(inputLabel);
  inputContainer.appendChild(inputBox);
  mainContent.appendChild(inputContainer);

  recorderContent.appendChild(mainContent);
  overlay.appendChild(recorderContent);
  if (document.body) {
    document.body.appendChild(overlay);
  } else {
    console.error('Cannot append overlay: document.body is not available');
  }

  const buttonRow = document.createElement('div');
  buttonRow.style.display = 'flex';
  buttonRow.style.justifyContent = 'space-between';
  buttonRow.style.gap = '10px';
  buttonRow.style.marginTop = '10px';

  mainContent.appendChild(buttonRow);
  const refreshBtn = document.createElement('button');
  refreshBtn.innerText = 'Update State';
  Object.assign(refreshBtn.style, {
    marginTop: '10px',
    background: '#007bff',
    color: '#fff',
    padding: '3px 8px',
    border: 'none',
    borderRadius: '6px',
    cursor: 'pointer',
  });
  refreshBtn.onclick = () => {
    window.notifyPython?.('control', { action: 'update' });
  };
  refreshBtn.style.flex = '1';
  buttonRow.appendChild(refreshBtn);

  const closeBtn = document.createElement('button');
  closeBtn.innerText = 'Close';
  Object.assign(closeBtn.style, {
    marginTop: '10px',
    background: '#dc3545',
    color: '#fff',
    padding: '3px 8px',
    border: 'none',
    borderRadius: '6px',
    cursor: 'pointer',
  });

  closeBtn.onclick = () => {
    window.notifyPython?.('control', { action: 'close' });
    let countdown = 3;
    closeBtn.innerText = `Close (${countdown})`;
    const intervalId = setInterval(() => {
      countdown -= 1;
      closeBtn.innerText = `Close (${countdown})`;
      if (countdown === 0) {
        clearInterval(intervalId);
        overlay.remove();
      }
    }, 1000);
  };
  closeBtn.style.flex = '1';
  buttonRow.appendChild(closeBtn);

  let currentTypedText = '';
  let recordingState = recording;

  function setRecordingState(state) {
    recordingState = state;

    toggleBtn.style.display = 'inline-block';
    refreshBtn.style.display = state ? 'inline-block' : 'none';
    toggleBtn.textContent = state ? 'Stop' : 'Start';
    toggleBtn.style.background = state ? '#e53935' : '#4CAF50';
  }

  function isRecording() {
    return recordingState;
  }

  let isDragging = false;
  let offsetX = 0,
    offsetY = 0;
  let initialOverlayLeft = 0;
  let initialOverlayTop = 0;

  header.onmousedown = (e) => {
    isDragging = true;
    const rect = overlay.getBoundingClientRect();
    offsetX = e.clientX - rect.left;
    offsetY = e.clientY - rect.top;
    initialOverlayLeft = rect.left;
    initialOverlayTop = rect.top;
    document.body.style.userSelect = 'none';
  };

  document.onmouseup = () => {
    isDragging = false;
    document.body.style.userSelect = 'auto';
  };

  document.onmousemove = (e) => {
    if (isDragging) {
      const newLeft = e.clientX - offsetX;
      const newTop = e.clientY - offsetY;

      overlay.style.left = `${newLeft}px`;
      overlay.style.top = `${newTop}px`;
      overlay.style.right = 'auto';

      if (sidePanel.style.display !== 'none') {
        sidePanel.style.top = `${newTop}px`;
        sidePanel.style.left = `${newLeft - sidePanel.offsetWidth - 20}px`; // 20px gap
        sidePanel.style.right = 'auto';
      }
    }
  };

  toggleBtn.onclick = () => {
    const newState = !isRecording();
    setRecordingState(newState);
    window.notifyPython?.('control', { action: newState ? 'start' : 'finish' });
    if (!newState) {
      // Clear the history list when recording is stopped
      while (historyList.firstChild) {
        historyList.removeChild(historyList.firstChild);
      }
    }
  };

  const printToOutput = ({ text, isNew = true }) => {
    if (isNew) {
      const line = document.createElement('div');
      line.textContent = text;
      Object.assign(line.style, {
        background: '#2a2a2a',
        padding: '3px 5px',
        marginBottom: '8px',
        borderRadius: '4px',
        boxSizing: 'border-box',
        width: '100%',
        wordBreak: 'break-word',
        fontSize: '13px',
        color: '#fff',
        border: '1px solid #3a3a3a',
      });
      outputBox.appendChild(line);
    } else {
      const lastLine = outputBox.lastElementChild;
      if (lastLine) {
        lastLine.textContent += text;
      } else {
        const line = document.createElement('div');
        line.textContent = text;
        Object.assign(line.style, {
          background: '#2a2a2a',
          padding: '3px 5px',
          marginBottom: '8px',
          borderRadius: '4px',
          boxSizing: 'border-box',
          width: '100%',
          wordBreak: 'break-word',
          fontSize: '13px',
          color: '#fff',
          border: '1px solid #3a3a3a',
        });
        outputBox.appendChild(line);
      }
    }
    outputBox.scrollTop = outputBox.scrollHeight; // Scroll to the latest line
  };
  const renderWorkflowStep = ({ step, action }) => {
    const container = document.createElement('div');
    container.style.display = 'flex';
    container.style.alignItems = 'flex-start';
    container.style.gap = '12px';
    container.style.position = 'relative';

    const dot = document.createElement('div');
    dot.style.width = '12px';
    dot.style.height = '12px';
    dot.style.borderRadius = '50%';
    dot.style.background = '#4CAF50';
    dot.style.marginTop = '4px';
    dot.style.flexShrink = '0';
    if (/type|enter/i.test(action)) {
      dot.style.background = '#ff9800'; // orange
    } else {
      dot.style.background = '#4CAF50'; // green
    }

    const info = document.createElement('div');
    info.style.display = 'flex';
    info.style.flexDirection = 'column';

    const actionText = document.createElement('div');
    actionText.innerText = `🛠 ${action}`;
    actionText.style.fontWeight = 'bold';

    info.appendChild(actionText);

    container.appendChild(dot);
    container.appendChild(info);
    container.dataset.stepIndex = step;

    historyList.appendChild(container);
  };

  const keydownHandler = (e) => {
    console.log('keydown event triggered');
    if (!isRecording) return;

    if (e.key.length === 1) {
      currentTypedText += e.key;
    } else if (e.key === 'Backspace') {
      currentTypedText = currentTypedText.slice(0, -1);
    } else if (e.key === 'Enter' || e.key === 'Tab') {
      if (currentTypedText) {
        window.notifyPython?.('elementType', {
          text: currentTypedText,
          mode: 'enter',
        });
        currentTypedText = '';
      }
    }
  };

  const clickHandler = (event) => {
    console.log('click event triggered');
    if (!isRecording) return;

    // Check if the click is on the recorder UI
    if (overlay.contains(event.target)) return;

    if (currentTypedText) {
      console.log('sending type-then-click');
      window.notifyPython?.('elementType', {
        text: currentTypedText,
        mode: 'type-then-click',
      });
      currentTypedText = '';
    }

    const attributes = {};
    for (let attr of event.target.attributes) {
      attributes[attr.name] = attr.value;
    }

    window.notifyPython?.('elementClick', { attributes });
  };

  const popstateHandler = () => {
    console.log('popstate event triggered');
    if (!isRecording) return;
    window.notifyPython?.('navigate', { url: window.location.href });
  };

  const loadHandler = () => {
    console.log('load event triggered');
    if (!isRecording) return;
    window.notifyPython?.('navigate', { url: window.location.href });
  };

  // Attach event listeners when the script first executes
  document.addEventListener('keydown', keydownHandler);
  document.keydownHandlerAttached = true;

  document.addEventListener('click', clickHandler);
  document.clickHandlerAttached = true;

  window.addEventListener('popstate', popstateHandler);
  window.popstateHandlerAttached = true;

  window.addEventListener('load', loadHandler);
  window.loadHandlerAttached = true;

  window.AgentRecorder = {
    refreshListeners: () => {
      console.log('Reattaching event listeners if not already attached');

      // Check and attach keydown event listener
      if (document.keydownHandlerAttached) {
        console.log('keydown event listener already attached');
      } else {
        console.log('attaching keydown event listener');
        document.addEventListener('keydown', keydownHandler);
        document.keydownHandlerAttached = true;
      }

      // Check and attach click event listener
      if (document.clickHandlerAttached) {
        console.log('click event listener already attached');
      } else {
        console.log('attaching click event listener');
        document.addEventListener('click', clickHandler);
        document.clickHandlerAttached = true;
      }

      // Check and attach popstate event listener
      if (window.popstateHandlerAttached) {
        console.log('popstate event listener already attached');
      } else {
        console.log('attaching popstate event listener');
        window.addEventListener('popstate', popstateHandler);
        window.popstateHandlerAttached = true;
      }

      // Check and attach load event listener
      if (window.loadHandlerAttached) {
        console.log('load event listener already attached');
      } else {
        console.log('attaching load event listener');
        window.addEventListener('load', loadHandler);
        window.loadHandlerAttached = true;
      }
    },
    requestOutput: (text) => {
      printToOutput({ text: text, isNew: true });
    },
    requestInput: ({ mode, question, placeholder = '', choices = [] }) => {
      inputLabel.innerText = question;
      while (inputBox.firstChild) {
        inputBox.removeChild(inputBox.firstChild);
      }
      inputContainer.style.display = 'block';

      if (mode === 'text') {
        const inputWrapper = document.createElement('div');
        inputWrapper.style = 'display: flex; align-items: center; gap: 6px;';

        const input = document.createElement('input');
        input.type = 'text';
        input.placeholder = placeholder;
        input.style = `
            flex: 1;
            padding: 8px;
            border-radius: 6px;
            border: none;
            font-size: 15px;
            background: #f0f0f0;
            color: #000;
          `;

        const submitBtn = document.createElement('button');
        const arrowIcon = document.createElementNS(
          'http://www.w3.org/2000/svg',
          'svg'
        );
        arrowIcon.setAttribute('width', '16');
        arrowIcon.setAttribute('height', '16');
        arrowIcon.setAttribute('fill', 'white');
        arrowIcon.setAttribute('viewBox', '0 0 16 16');

        const path = document.createElementNS(
          'http://www.w3.org/2000/svg',
          'path'
        );
        path.setAttribute('fill-rule', 'evenodd');
        path.setAttribute(
          'd',
          'M1.5 8a.5.5 0 0 1 .5-.5h10.793L9.146 5.354a.5.5 0 1 1 .708-.708l4 4a.498.498 0 0 1 .106.168.5.5 0 0 1-.106.54l-4 4a.5.5 0 0 1-.708-.708L12.793 8.5H2a.5.5 0 0 1-.5-.5z'
        );
        arrowIcon.appendChild(path);

        submitBtn.appendChild(arrowIcon);
        submitBtn.title = 'Submit';
        submitBtn.style = `
            background: #7e57c2;
            color: white;
            border: none;
            border-radius: 6px;
            padding: 8px 10px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
          `;

        submitBtn.onclick = () => {
          window.notifyPython('submitOverlayInput', input.value);
          inputContainer.style.display = 'none';
        };

        inputWrapper.appendChild(input);
        inputWrapper.appendChild(submitBtn);
        inputBox.appendChild(inputWrapper);
      } else if (mode === 'radio' || mode === 'checkbox') {
        choices.forEach((choice, idx) => {
          const id = `choice-${idx}`;

          const wrapper = document.createElement('div');
          wrapper.style = `
              display: flex;
              align-items: center;
              padding: 8px 12px;
              margin-bottom: 8px;
              border-radius: 8px;
              background: #2c2c2c;
              cursor: pointer;
              transition: background 0.2s;
            `;
          wrapper.onmouseenter = () => (wrapper.style.background = '#3a3a3a');
          wrapper.onmouseleave = () => (wrapper.style.background = '#2c2c2c');

          const input = document.createElement('input');
          input.type = mode;
          input.name = 'overlay-input';
          input.value = choice;
          input.id = id;
          input.style.marginRight = '10px';

          const label = document.createElement('label');
          label.htmlFor = id;
          label.textContent = choice;
          label.style = `
              flex: 1;
              color: #fff;
              cursor: pointer;
            `;

          wrapper.appendChild(input);
          wrapper.appendChild(label);
          inputBox.appendChild(wrapper);
        });

        const submit = document.createElement('button');
        const arrowIcon = document.createElementNS(
          'http://www.w3.org/2000/svg',
          'svg'
        );
        arrowIcon.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
        arrowIcon.setAttribute('width', '16');
        arrowIcon.setAttribute('height', '16');
        arrowIcon.setAttribute('fill', 'white');
        arrowIcon.setAttribute('viewBox', '0 0 16 16');

        const path = document.createElementNS(
          'http://www.w3.org/2000/svg',
          'path'
        );
        path.setAttribute('fill-rule', 'evenodd');
        path.setAttribute(
          'd',
          'M1.5 8a.5.5 0 0 1 .5-.5h10.793L9.146 5.354a.5.5 0 1 1 .708-.708l4 4a.498.498 0 0 1 .106.168.5.5 0 0 1-.106.54l-4 4a.5.5 0 0 1-.708-.708L12.793 8.5H2a.5.5 0 0 1-.5-.5z'
        );
        arrowIcon.appendChild(path);

        const submitText = document.createElement('span');
        submitText.textContent = 'Submit';

        submit.appendChild(arrowIcon);
        submit.appendChild(submitText);
        submit.style = `
            margin-top: 12px;
            padding: 8px 14px;
            border-radius: 6px;
            border: none;
            background: #7e57c2;
            color: white;
            font-weight: bold;
            font-size: 14px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 6px;
          `;
        submit.onclick = () => {
          const values = Array.from(
            inputBox.querySelectorAll(`input[name='overlay-input']:checked`)
          ).map((e) => e.value);
          const singleValue = inputBox.querySelector(
            `input[name='overlay-input']:checked`
          )?.value;
          const final = mode === 'radio' ? singleValue : values;
          window.notifyPython('submitOverlayInput', final);
          inputContainer.style.display = 'none';
        };
        inputBox.appendChild(submit);
      }
    },
    addWorkflowStep: (action) => {
      const step = historyList.children.length;
      renderWorkflowStep({ step, action });
    },
  };
  setTimeout(() => {
    window.AgentRecorder.setRecording = (state) => {
      setRecordingState(state);
    };
  }, 0);

  setRecordingState(recording); // Initial sync
})(false);
