import { useState, useEffect } from 'react';
import { View, Text, TextInput, FlatList, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as SecureStore from 'expo-secure-store';
import { track } from '../../utils/tracking';

type Message = {
  id: string;
  text: string;
  sender: 'user' | 'ai' | 'system';
};

export default function ChatScreen() {
  useEffect(() => {
    track('app_launch', {
      screen: 'Chat',
      timestamp: new Date().toISOString()
    });
  }, []);

  const [messages, setMessages] = useState<Message[]>([
    { id: '1', text: 'Hello! I can help with math problems. Ask me anything!', sender: 'ai' }
  ]);
  const [inputText, setInputText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSend = async () => {
    if (!inputText.trim() || isLoading) return;
    
    const userMessage: Message = {
      id: Date.now().toString(),
      text: inputText,
      sender: 'user'
    };
    setMessages(prev => [...prev, userMessage]);
    setInputText('');
    setIsLoading(true);
    setError('');
    
    try {
      const response = await fetch('http://localhost:8000/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message: inputText })
      });

      if (!response.ok) {
        if (response.status === 429) {
          const errorData = await response.json();
          setMessages(prev => [...prev, {
            id: Date.now().toString() + '-limit',
            text: errorData.detail || 'Daily free limit reached. Please sign in to continue.',
            sender: 'system'
          }]);
          return;
        }
        throw new Error(`API error: ${response.status}`);
      }

      const data = await response.json();
      
      if (data.remaining <= 50) {  // Warn when low
        setMessages(prev => [...prev, {
          id: Date.now().toString() + '-warning',
          text: `Warning: You have ${data.remaining} tokens remaining today`,
          sender: 'system'
        }]);
      }

      const aiMessage: Message = {
        id: (Date.now() + 1).toString(),
        text: data.response,
        sender: 'ai'
      };
      setMessages(prev => [...prev, aiMessage]);
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Request failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <View style={styles.container}>
      <FlatList
        data={messages}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => (
          <View style={[
            styles.messageBubble, 
            item.sender === 'user' ? styles.userBubble : 
            item.sender === 'ai' ? styles.aiBubble : styles.systemBubble
          ]}>
            <Text style={styles.messageText}>{item.text}</Text>
          </View>
        )}
        contentContainerStyle={styles.messagesContainer}
      />

      {isLoading && (
        <ActivityIndicator style={styles.loadingIndicator} size="small" />
      )}

      {error && (
        <Text style={styles.errorText}>{error}</Text>
      )}

      <View style={styles.inputContainer}>
        <TextInput
          style={styles.input}
          value={inputText}
          onChangeText={setInputText}
          placeholder="Type your math question..."
          editable={!isLoading}
        />
        <TouchableOpacity 
          style={styles.sendButton} 
          onPress={handleSend}
          disabled={isLoading}
        >
          <Ionicons name="send" size={24} color="white" />
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  messagesContainer: {
    padding: 10,
  },
  messageBubble: {
    padding: 12,
    borderRadius: 8,
    marginVertical: 4,
    maxWidth: '80%',
  },
  userBubble: {
    alignSelf: 'flex-end',
    backgroundColor: '#4CAF50',
  },
  aiBubble: {
    alignSelf: 'flex-start',
    backgroundColor: '#333',
  },
  systemBubble: {
    alignSelf: 'center',
    backgroundColor: '#ccc',
  },
  messageText: {
    color: 'white',
  },
  inputContainer: {
    flexDirection: 'row',
    padding: 10,
    backgroundColor: 'white',
    alignItems: 'center',
  },
  input: {
    flex: 1,
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 20,
    padding: 10,
    marginRight: 10,
  },
  sendButton: {
    backgroundColor: '#4CAF50',
    borderRadius: 20,
    padding: 10,
  },
  loadingIndicator: {
    marginVertical: 10,
  },
  errorText: {
    color: 'red',
    textAlign: 'center',
    padding: 10,
  },
});
