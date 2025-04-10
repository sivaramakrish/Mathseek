import { useState, useEffect, useRef } from 'react';
import {
  View,
  Text,
  TextInput,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Alert
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as SecureStore from 'expo-secure-store';
import { track } from '../../utils/tracking';

type Message = {
  id: string;
  text: string;
  sender: 'user' | 'ai' | 'system';
};

export default function ChatScreen() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      text: 'Hello! I can help with math problems. Ask me anything!',
      sender: 'ai'
    }
  ]);
  const [inputText, setInputText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const flatListRef = useRef<FlatList>(null);

  const handleTokenError = async (error: any) => {
    if (error?.status === 429) {
      Alert.alert(
        "Limit Reached",
        "Maximum anonymous users reached today. Please try again tomorrow or register for full access."
      );
      return null;
    }
    Alert.alert("Error", "Failed to get anonymous token");
    return null;
  };

  const getAnonymousToken = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/anonymous/token', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        }
      });
      
      if (!response.ok) {
        return await handleTokenError({
          status: response.status,
          response: response
        });
      }
      return await response.json();
    } catch (error) {
      return await handleTokenError(error);
    }
  };

  const handleSend = async () => {
    const trimmedText = inputText.trim();
    if (!trimmedText) return;

    try {
      setIsLoading(true);
      setError('');

      // Add user message immediately
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        text: trimmedText,
        sender: 'user'
      }]);
      setInputText('');

      let anonymousToken = await SecureStore.getItemAsync('anonymousToken');
      const headers: Record<string, string> = {
        'Content-Type': 'application/json'
      };

      if (!anonymousToken) {
        const tokenData = await getAnonymousToken();
        if (!tokenData) {
          setIsLoading(false);
          return;
        }
        anonymousToken = tokenData.token;
        await SecureStore.setItemAsync('anonymousToken', anonymousToken);
      }

      headers['X-Anonymous-Token'] = anonymousToken;

      const response = await fetch('http://localhost:8000/chat', {
        method: 'POST',
        headers,
        body: JSON.stringify({ message: trimmedText })
      });

      if (!response.ok) {
        throw new Error(await response.text());
      }

      const responseData = await response.json();
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        text: responseData.response,
        sender: 'ai'
      }]);
    } catch (error) {
      setError('Failed to send message');
      console.error('Chat error:', error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    track('app_launch', {
      screen: 'Chat',
      timestamp: new Date().toISOString()
    });
  }, []);

  useEffect(() => {
    if (messages.length > 0) {
      flatListRef.current?.scrollToEnd({ animated: true });
    }
  }, [messages]);

  return (
    <View style={styles.container}>
      <FlatList
        ref={flatListRef}
        data={messages}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => (
          <View style={[
            styles.messageContainer,
            item.sender === 'user' ? styles.userMessage : styles.aiMessage
          ]}>
            <Text style={styles.messageText}>{item.text}</Text>
          </View>
        )}
        contentContainerStyle={styles.messagesList}
      />

      {error ? <Text style={styles.errorText}>{error}</Text> : null}

      <View style={styles.inputContainer}>
        <TextInput
          style={styles.input}
          value={inputText}
          onChangeText={setInputText}
          placeholder="Type your math question..."
          placeholderTextColor="#999"
          editable={!isLoading}
        />
        <TouchableOpacity
          style={styles.sendButton}
          onPress={handleSend}
          disabled={isLoading || !inputText.trim()}
        >
          {isLoading ? (
            <ActivityIndicator size="small" color="#fff" />
          ) : (
            <Ionicons name="send" size={24} color="white" />
          )}
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
  messagesList: {
    padding: 16,
  },
  messageContainer: {
    maxWidth: '80%',
    padding: 12,
    borderRadius: 8,
    marginBottom: 8,
  },
  userMessage: {
    alignSelf: 'flex-end',
    backgroundColor: '#007bff',
  },
  aiMessage: {
    alignSelf: 'flex-start',
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#ddd',
  },
  messageText: {
    fontSize: 16,
    color: '#333',
  },
  userMessageText: {
    color: 'white',
  },
  inputContainer: {
    flexDirection: 'row',
    padding: 8,
    backgroundColor: '#fff',
    borderTopWidth: 1,
    borderTopColor: '#ddd',
  },
  input: {
    flex: 1,
    padding: 12,
    backgroundColor: '#fff',
    borderRadius: 24,
    borderWidth: 1,
    borderColor: '#ddd',
    marginRight: 8,
  },
  sendButton: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: '#007bff',
    justifyContent: 'center',
    alignItems: 'center',
  },
  errorText: {
    color: 'red',
    textAlign: 'center',
    padding: 8,
  },
});