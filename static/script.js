let currentUser = null;
let eventSource = null;  // Added global variable

// Load users and set up real-time updates when the page loads
document.addEventListener('DOMContentLoaded', () => {
    loadUsers();
    setupEventSource();
    setInterval(refreshMessages, 10);  // Refresh messages every 3 seconds
});

// Load the list of users from the server
async function loadUsers() {
    try {
        const response = await fetch('/get_users');
        const data = await response.json();
        const userList = document.querySelector('.users-list');
        userList.innerHTML = ''; // Clear existing users
        
        // Add each user to the list
        data.users.forEach(user => {
            const div = document.createElement('div');
            div.className = 'user-item';
            div.textContent = user;
            div.dataset.username = user;
            
            // Add click event listener to each user item
            div.addEventListener('click', () => selectUser(user));
            
            userList.appendChild(div);
        });
    } catch (error) {
        console.error('Failed to load users:', error);
    }
}

// Handle user selection
function selectUser(username) {
    currentUser = username;
    
    // Update active state for user items
    document.querySelectorAll('.user-item').forEach(item => {
        item.classList.toggle('active', item.dataset.username === username);
    });
    
    // Enable message input and set placeholder
    document.getElementById('messageInput').disabled = false;
    document.getElementById('messageInput').placeholder = `Message ${username}...`;
    
    // Load messages for the selected user
    refreshMessages();
}

// Updated setupEventSource function
function setupEventSource() {
    if (eventSource) {
        eventSource.close();
    }

    const username = '{{ username }}';  // Get the username from the template
    eventSource = new EventSource(`/stream?username=${encodeURIComponent(username)}`);
    
    eventSource.onopen = () => {
        console.log('SSE connection established');
    };
    
    eventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            const messageList = document.getElementById('messageList');
            
            // Simplified message display for testing
            const div = document.createElement('div');
            div.className = `message ${data.sender === '{{ username }}' ? 'sent' : 'received'}`;
            div.innerHTML = `
                <div>${data.message}</div>
                <span class="timestamp">${new Date(data.timestamp).toLocaleString()}</span>
            `;
            messageList.appendChild(div);
            messageList.scrollTop = messageList.scrollHeight;
        } catch (error) {
            console.error('Error processing SSE message:', error);
        }
    };
    
    eventSource.onerror = (error) => {
        console.log('SSE error:', error);
        setTimeout(() => {
            console.log('Attempting SSE reconnect...');
            setupEventSource();
        }, 3000);
    };
}

// Send a message to the selected user
async function sendMessage() {
    if (!currentUser) {
        alert('Please select a user to chat with');
        return;
    }

    const message = document.getElementById('messageInput').value;
    if (!message) {
        alert('Please enter a message');
        return;
    }

    try {
        // Immediately display the sent message in the chat area
        const messageList = document.getElementById('messageList');
        const div = document.createElement('div');
        div.className = 'message sent';
        div.innerHTML = `
            <div>${message}</div>
            <span class="timestamp">${new Date().toLocaleString()}</span>
        `;
        messageList.appendChild(div);
        messageList.scrollTop = messageList.scrollHeight;

        // Send the message to the server
        await fetch('/send', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                receiver: currentUser,
                message: message
            })
        });
        
        // Clear the input field after sending
        document.getElementById('messageInput').value = '';
    } catch (error) {
        console.error('Failed to send message:', error);
        alert('Failed to send message. Please try again.');
    }
}

// Refresh messages for the selected user
async function refreshMessages() {
    if (!currentUser) {
        document.getElementById('messageList').innerHTML = '<div class="info-message">Select a user to start chatting</div>';
        return;
    }
    
    try {
        const response = await fetch(`/get_user_messages/${currentUser}`);
        const data = await response.json();
        const messageList = document.getElementById('messageList');
        messageList.innerHTML = ''; // Clear existing messages
        
        if (data.messages.length === 0) {
            messageList.innerHTML = '<div class="info-message">No messages yet. Start the conversation!</div>';
            return;
        }
        
        // Display all messages for the selected user
        data.messages.forEach(msg => {
            const div = document.createElement('div');
            div.className = `message ${msg.direction}`;
            
            const content = document.createElement('div');
            content.textContent = msg.message;
            
            const timestamp = document.createElement('span');
            timestamp.className = 'timestamp';
            timestamp.textContent = new Date(msg.timestamp).toLocaleString();
            
            div.appendChild(content);
            div.appendChild(timestamp);
            messageList.appendChild(div);
        });
        
        // Auto-scroll to the bottom of the message list
        messageList.scrollTop = messageList.scrollHeight;
    } catch (error) {
        console.error('Failed to refresh messages:', error);
    }
}