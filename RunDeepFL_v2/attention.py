from __future__ import print_function
import input
import tensorflow as tf
tf.compat.v1.disable_eager_execution()
tf.estimator.ProfilerHook(10)
import time
from config import *
import utils as ut
class MultiHeadAttention(tf.keras.layers.Layer):
  def __init__(self, d_model, num_heads):
    super(MultiHeadAttention, self).__init__()
    self.num_heads = num_heads
    self.d_model = d_model
    
    assert d_model % self.num_heads == 0
    
    self.depth = d_model // self.num_heads
    
    self.wq = tf.keras.layers.Dense(d_model)
    self.wk = tf.keras.layers.Dense(d_model)
    self.wv = tf.keras.layers.Dense(d_model)
    
    self.dense = tf.keras.layers.Dense(d_model)
        
  def split_heads(self, x, batch_size):
    """分拆最后一个维度到 (num_heads, depth).
    转置结果使得形状为 (batch_size, num_heads, seq_len, depth)
    """
    x = tf.reshape(x, (batch_size, -1, self.num_heads, self.depth))
    return tf.transpose(x, perm=[0, 2, 1, 3])
    
  def call(self, v, k, q, mask = None):
    batch_size = tf.shape(q)[0]
    
    # q = self.wq(q)  # (batch_size, seq_len, d_model)
    # k = self.wk(k)  # (batch_size, seq_len, d_model)
    # v = self.wv(v)  # (batch_size, seq_len, d_model)
    
    q = self.split_heads(q, batch_size)  # (batch_size, num_heads, seq_len_q, depth)
    k = self.split_heads(k, batch_size)  # (batch_size, num_heads, seq_len_k, depth)
    v = self.split_heads(v, batch_size)  # (batch_size, num_heads, seq_len_v, depth)
    
    # scaled_attention.shape == (batch_size, num_heads, seq_len_q, depth)
    # attention_weights.shape == (batch_size, num_heads, seq_len_q, seq_len_k)
    scaled_attention, attention_weights = scaled_dot_product_attention(
        q, k, v, mask)
    
    scaled_attention = tf.transpose(scaled_attention, perm=[0, 2, 1, 3])  # (batch_size, seq_len_q, num_heads, depth)

    concat_attention = tf.reshape(scaled_attention, 
                                  (batch_size, -1, self.d_model))  # (batch_size, seq_len_q, d_model)

    output = self.dense(concat_attention)  # (batch_size, seq_len_q, d_model)
        
    return output, attention_weights


def scaled_dot_product_attention(q, k, v, mask = None):
  """计算注意力权重。
  q, k, v 必须具有匹配的前置维度。
  k, v 必须有匹配的倒数第二个维度，例如：seq_len_k = seq_len_v。
  虽然 mask 根据其类型（填充或前瞻）有不同的形状，
  但是 mask 必须能进行广播转换以便求和。
  
  参数:
    q: 请求的形状 == (..., seq_len_q, depth)
    k: 主键的形状 == (..., seq_len_k, depth)
    v: 数值的形状 == (..., seq_len_v, depth_v)
    mask: Float 张量，其形状能转换成
          (..., seq_len_q, seq_len_k)。默认为None。
    
  返回值:
    输出，注意力权重
  """

  matmul_qk = tf.matmul(q, k, transpose_b=True)  # (..., seq_len_q, seq_len_k)
  
  # 缩放 matmul_qk
  dk = tf.cast(tf.shape(k)[-1], tf.float32)
  scaled_attention_logits = matmul_qk / tf.math.sqrt(dk)

  # 将 mask 加入到缩放的张量上。
  if mask is not None:
    scaled_attention_logits += (mask * -1e9)  

  # softmax 在最后一个轴（seq_len_k）上归一化，因此分数
  # 相加等于1。
  attention_weights = tf.nn.softmax(scaled_attention_logits, axis=-1)  # (..., seq_len_q, seq_len_k)

  output = tf.matmul(attention_weights, v)  # (..., seq_len_q, depth_v)

  return output, attention_weights


def single_fc_layer(input_layer,input_dimension,output_dimension,keep_prob,is_training):
    weight = create_variables("weight",[input_dimension, output_dimension])
    bias = tf.Variable(tf.random.normal([output_dimension]))
    output_layer = tf.add(tf.matmul(input_layer, weight), bias)
    output_layer = tf.nn.dropout(output_layer, 1 - (keep_prob))
    output_layer = tf.nn.relu(output_layer)
    return output_layer


'''
Add histogram summary and scalar summary of the sparsity of the tensor for tensor analysis
@param x: A tensor
@return N/A
'''
def activation_summary(x):
    tensor_name = x.op.name
    tf.compat.v1.summary.histogram(tensor_name + '/activations', x)
    tf.compat.v1.summary.scalar(tensor_name + '/sparsity', tf.nn.zero_fraction(x))
'''
Create tensor variables
@param name: tensor name
@param shape: tensor shape
@param initializer: tensor initializer
@return the created tensor
'''
def create_variables(name, shape, initializer=tf.compat.v1.keras.initializers.VarianceScaling(scale=1.0, mode="fan_avg", distribution="uniform")):
    regularizer = tf.keras.regularizers.l2(l=0.5 * (L2_value))
    new_variables = tf.compat.v1.get_variable(name, shape=shape, initializer=initializer,regularizer=regularizer)
    activation_summary(new_variables)
    return new_variables
'''
Define MLP_DFL_1 model
@param spec: tensor of spectrum-based features 
@param m1: tensor of first mutation-based features
@param m2: tensor of second mutation-based features
@param m3: tensor of third mutation-based features
@param m4: tensor of fourth mutation-based features
@param complexity: tensor of complexity-based features
@param similarity: tensor of textual similarity features
@param keep_prob: keep probability in drop-out layer, which is defined in config.py
@param is_training: boolean variable to indicate training or inference
@return tensor of prediction results
'''
def attention(spec, m1,m2,m3,m4,complexity,similarity, keep_prob,is_training):
    model_size_times = 2
    hidden_dim = 128
    num_heads = 4
    batch_size = tf.shape(m1)[0] 
    print(batch_size)
    with tf.compat.v1.variable_scope('seperate1',reuse=False):
        with tf.compat.v1.variable_scope('spec',reuse=False):
            #spec = tf.layers.batch_normalization(spec, training=is_training)
            spec_1 = single_fc_layer(spec,34,hidden_dim, keep_prob,is_training)
        with tf.compat.v1.variable_scope('mut1',reuse=False):
            #mutation = tf.layers.batch_normalization(mutation, training=is_training)
            mut_1 = single_fc_layer(m1,35,hidden_dim, keep_prob,is_training)
        with tf.compat.v1.variable_scope('mut2',reuse=False):
            #mutation = tf.layers.batch_normalization(mutation, training=is_training)
            mut_2 = single_fc_layer(m2,35,hidden_dim, keep_prob,is_training)
        with tf.compat.v1.variable_scope('mut3',reuse=False):
            #mutation = tf.layers.batch_normalization(mutation, training=is_training)
            mut_3 = single_fc_layer(m3,35,hidden_dim, keep_prob,is_training)
        with tf.compat.v1.variable_scope('mut4',reuse=False):
            #mutation = tf.layers.batch_normalization(mutation, training=is_training)
            mut_4 = single_fc_layer(m4,35,hidden_dim, keep_prob,is_training)
        with tf.compat.v1.variable_scope('complex',reuse=False):
            #complexity = tf.layers.batch_normalization(complexity, training=is_training)
            complex_1 = single_fc_layer(complexity,37,hidden_dim, keep_prob,is_training)
        with tf.compat.v1.variable_scope('similar',reuse=False):
            #similarity = tf.layers.batch_normalization(similarity, training=is_training)
            similar_1 = single_fc_layer(similarity,15,hidden_dim, keep_prob,is_training)
        with tf.compat.v1.variable_scope('query',reuse=False):
            query = tf.ones([batch_size,1]) 
            query = single_fc_layer(query,1,hidden_dim, keep_prob,is_training)   
            query = tf.expand_dims(query,1)  
    with tf.compat.v1.variable_scope('attention',reuse=False):
        key = tf.stack([spec_1,mut_1,mut_2,mut_3,mut_4,complex_1,similar_1],1)
        multihead_attention = MultiHeadAttention(d_model=hidden_dim, num_heads=4)
        output,_ = multihead_attention(key,key,query)
        output = tf.squeeze(output)
    print(output.get_shape())
    final_weight = create_variables("final_weight",[hidden_dim, 2])
    final_bias = tf.compat.v1.get_variable("final_bias", shape=[2], initializer=tf.compat.v1.zeros_initializer())
    output = tf.add(tf.matmul(output, final_weight), final_bias)
    print(output.get_shape())
    return output

'''
Main function for executing the model
@param trainFile: .csv filename of training features
@param trainLabelFile: .csv filename of training labels
@param testFile: .csv filename of test features
@param testLabelFile: .csv filename of test labels
@param groupFile: group filename
@param suspFile: output file name storing the prediction results of model, typically the results name will be suspFile+epoch_num
@param loss: the loss function configurations controlled in command
@param model_type: model configurations controlled in command
@param featureNum: number of input features
@param nodeNum: hidden node number per layer 
@return N/A
'''
def run(trainFile, trainLabelFile, testFile,testLabelFile, groupFile, suspFile,loss, model_type,featureNum, nodeNum):
    tf.compat.v1.reset_default_graph()
    # Network Parameters
    n_classes = 2 #  total output classes (0 or 1)
    n_input = featureNum # total number of input features
    n_hidden_1 = nodeNum # 1st layer number of nodes                                                                       
    train_writer = tf.compat.v1.summary.FileWriter("./log", graph=tf.compat.v1.get_default_graph())
    # tf Graph input
    x = tf.compat.v1.placeholder("float", [None, 226])
    spec = tf.compat.v1.placeholder("float", [None, 34])
    mutation1 = tf.compat.v1.placeholder("float", [None, 35])
    mutation2 = tf.compat.v1.placeholder("float", [None, 35])
    mutation3 = tf.compat.v1.placeholder("float", [None, 35])
    mutation4 = tf.compat.v1.placeholder("float", [None, 35])
    mutation = tf.compat.v1.placeholder("float", [None, 140])
    complexity = tf.compat.v1.placeholder("float", [None, 37])
    similarity = tf.compat.v1.placeholder("float", [None, 15])
    y = tf.compat.v1.placeholder("float", [None, n_classes])
    g = tf.compat.v1.placeholder(tf.int32, [None, 1])
    is_training = tf.compat.v1.placeholder(tf.bool, name='is_training')
    
    # dropout parameter
    keep_prob = tf.compat.v1.placeholder(tf.float32)

    # Construct model
    if model_type == "attention":
        pred = attention(spec, mutation1,mutation2,mutation3,mutation4,complexity,similarity, keep_prob,is_training) 
    # elif model_type == "dfl1-Spectrum":
    #     pred = fc_2_layers_spec(spec, mutation1,mutation2,mutation3,mutation4,complexity,similarity, keep_prob,is_training) 
    # elif model_type == "dfl1-Mutation":
    #     pred = fc_2_layers_mut(spec, mutation1,mutation2,mutation3,mutation4,complexity,similarity, keep_prob,is_training) 
    # elif model_type == "dfl1-Metrics":
    #     pred = fc_2_layers_complex(spec, mutation1,mutation2,mutation3,mutation4,complexity,similarity, keep_prob,is_training) 
    # elif model_type == "dfl1-Textual":
    #     pred = fc_2_layers_similar(spec, mutation1,mutation2,mutation3,mutation4,complexity,similarity, keep_prob,is_training) 
    datasets = input.read_data_sets(trainFile, trainLabelFile, testFile, testLabelFile, groupFile)
    # Define loss and optimizer                          
    regu_losses = tf.compat.v1.get_collection(tf.compat.v1.GraphKeys.REGULARIZATION_LOSSES)
    y = tf.stop_gradient(y)
    cost = ut.loss_func(pred, y, loss, datasets,g)
    update_ops = tf.compat.v1.get_collection(tf.compat.v1.GraphKeys.UPDATE_OPS)
    summary_op = tf.compat.v1.summary.merge_all()
    with tf.control_dependencies(update_ops):
        optimizer = tf.compat.v1.train.AdamOptimizer(learning_rate=learning_rate).minimize(cost+regu_losses)

    # Initializing the variables
    init = tf.compat.v1.global_variables_initializer()

    # Launch the graph
    gpu_options = tf.compat.v1.GPUOptions(per_process_gpu_memory_fraction=0.2)
    with tf.compat.v1.Session(config=tf.compat.v1.ConfigProto(gpu_options=gpu_options)) as sess:
        sess.run(init)

        # Training cycle
        for epoch in range(training_epochs):
            avg_cost = 0.
            total_batch = int(datasets.train.num_instances/batch_size)
            # Loop over all batches
            for i in range(total_batch):
                batch_x, batch_y ,batch_g= datasets.train.next_batch(batch_size)
                # Run optimization op (backprop) and cost op (to get loss value)
                
                _, c,regu_loss = sess.run([optimizer, cost,regu_losses], feed_dict={  spec : batch_x[:,:34],
                                                                mutation1 : batch_x[:,34:69],
                                                                mutation2 : batch_x[:,69:104],
                                                                mutation3 : batch_x[:,104:139],
                                                                mutation4 : batch_x[:,139:174],
                                                                complexity : batch_x[:,174:211],
                                                                similarity : batch_x[:,-15:],
                                                                y: batch_y, g: batch_g, keep_prob: dropout_rate,is_training:True})
                # Compute average loss
                avg_cost += c / total_batch
            # Display logs per epoch step
            
            if epoch % display_step == 0:
                print("Epoch:", '%04d' % (epoch+1), "cost=", \
                    "{:.9f}".format(avg_cost),", l2 loss= ",numpy.sum(regu_loss))
            
            if epoch % dump_step ==(dump_step-1):
                #Write Result
                
                res,step_summary=sess.run([tf.nn.softmax(pred),summary_op],feed_dict={spec : datasets.test.instances[:,:34],
                                                                mutation1 : datasets.test.instances[:,34:69],
                                                                mutation2 : datasets.test.instances[:,69:104],
                                                                mutation3 : datasets.test.instances[:,104:139],
                                                                mutation4 : datasets.test.instances[:,139:174],
                                                                complexity : datasets.test.instances[:,174:211],
                                                                similarity : datasets.test.instances[:,-15:], y: datasets.test.labels, keep_prob: 1.0,is_training:False})
                train_writer.add_summary(step_summary)
                with open(suspFile+'-'+str(epoch+1),'w') as f:
                    for susp in res[:,0]:
                        f.write(str(susp)+'\n')

        #print(" Optimization Finished!")