from __future__ import print_function
import input
import tensorflow as tf
import time
from config import *
import utils as ut
def activation_summary(x):
    '''
    :param x: A Tensor
    :return: Add histogram summary and scalar summary of the sparsity of the tensor
    '''
    tensor_name = x.op.name
    tf.summary.histogram(tensor_name + '/activations', x)
    tf.summary.scalar(tensor_name + '/sparsity', tf.nn.zero_fraction(x))
def create_variables(name, shape, initializer=tf.contrib.layers.xavier_initializer()):
    regularizer = tf.contrib.layers.l2_regularizer(scale=L2_value)
    new_variables = tf.get_variable(name, shape=shape, initializer=initializer,regularizer=regularizer)
    activation_summary(new_variables)
    return new_variables

def single_fc_layer(input_layer,input_dimension,output_dimension,keep_prob,is_training):
    weight = create_variables("weight",[input_dimension, output_dimension])
    bias = tf.Variable(tf.random_normal([output_dimension]))
    output_layer = tf.add(tf.matmul(input_layer, weight), bias)
    output_layer = tf.nn.dropout(output_layer, keep_prob)
    output_layer = tf.nn.relu(output_layer)
    return output_layer

def mutation_spec_first(spec, m1,m2,m3,m4,complexity,similarity, keep_prob,is_training):
    model_size_times = 2
    with tf.variable_scope('seperate_mut',reuse=False):
        with tf.variable_scope('mut1',reuse=False):
            #mutation = tf.layers.batch_normalization(mutation, training=is_training)
            mut_1 = single_fc_layer(m1,35,35*model_size_times, keep_prob,is_training)
        with tf.variable_scope('mut2',reuse=False):
            #mutation = tf.layers.batch_normalization(mutation, training=is_training)
            mut_2 = single_fc_layer(m2,35,35*model_size_times, keep_prob,is_training)
        with tf.variable_scope('mut3',reuse=False):
            #mutation = tf.layers.batch_normalization(mutation, training=is_training)
            mut_3 = single_fc_layer(m3,35,35*model_size_times, keep_prob,is_training)
        with tf.variable_scope('mut4',reuse=False):
            #mutation = tf.layers.batch_normalization(mutation, training=is_training)
            mut_4 = single_fc_layer(m4,35,35*model_size_times, keep_prob,is_training)
        mut_concat = tf.concat([mut_1,mut_2,mut_3,mut_4],1)
        with tf.variable_scope('mut_concat',reuse=False):
            mut_concat = single_fc_layer(mut_concat,35*4*model_size_times,35*model_size_times, keep_prob,is_training)

    with tf.variable_scope('seperate_spec',reuse=False):
        with tf.variable_scope('spec',reuse=False):
            #spec = tf.layers.batch_normalization(spec, training=is_training)
            spec_1 = single_fc_layer(spec,34,34*model_size_times, keep_prob,is_training)
        spec_concat = tf.concat([spec_1,mut_concat],1)
        with tf.variable_scope('fc1',reuse=False):
            spec_concat = single_fc_layer(spec_concat,69*model_size_times,32*model_size_times, keep_prob,is_training)
    with tf.variable_scope('fc',reuse=False):
        with tf.variable_scope('complex',reuse=False):
            #complexity = tf.layers.batch_normalization(complexity, training=is_training)
            complex_1 = single_fc_layer(complexity,37,37*model_size_times, keep_prob,is_training)
        with tf.variable_scope('similar',reuse=False):
            #similarity = tf.layers.batch_normalization(similarity, training=is_training)
            similar_1 = single_fc_layer(similarity,15,15*model_size_times, keep_prob,is_training)
        fc_1 = tf.concat([spec_concat,complex_1,similar_1],1)
        with tf.variable_scope('fc1',reuse=False):
            fc_2 = single_fc_layer(fc_1,84*model_size_times,128, keep_prob,is_training)
    final_weight = create_variables("final_weight",[128, 2])
    final_bias = tf.get_variable("final_bias", shape=[2], initializer=tf.zeros_initializer())
    out_layer = tf.add(tf.matmul(fc_2, final_weight), final_bias)
    return out_layer
    
def run(trainFile, trainLabelFile, testFile,testLabelFile, groupFile, suspFile,loss, featureNum, nodeNum):
    tf.reset_default_graph()
    # Network Parameters
    n_classes = 2 #  total output classes (0 or 1)
    n_input = featureNum # total number of input features
    n_hidden_1 = nodeNum # 1st layer number of nodes                                                                       
    train_writer = tf.summary.FileWriter("./log", graph=tf.get_default_graph())
    # tf Graph input
    x = tf.placeholder("float", [None, 226])
    spec = tf.placeholder("float", [None, 34])
    mutation1 = tf.placeholder("float", [None, 35])
    mutation2 = tf.placeholder("float", [None, 35])
    mutation3 = tf.placeholder("float", [None, 35])
    mutation4 = tf.placeholder("float", [None, 35])
    mutation = tf.placeholder("float", [None, 140])
    complexity = tf.placeholder("float", [None, 37])
    similarity = tf.placeholder("float", [None, 15])
    y = tf.placeholder("float", [None, n_classes])
    g = tf.placeholder(tf.int32, [None, 1])
    is_training = tf.placeholder(tf.bool, name='is_training')
    
    # dropout parameter
    keep_prob = tf.placeholder(tf.float32)

    # Construct model
    pred = mutation_spec_first(spec, mutation1,mutation2,mutation3,mutation4,complexity,similarity, keep_prob,is_training) 
    datasets = input.read_data_sets(trainFile, trainLabelFile, testFile, testLabelFile, groupFile)


    # Define loss and optimizer                          
    regu_losses = tf.get_collection(tf.GraphKeys.REGULARIZATION_LOSSES)
    y = tf.stop_gradient(y)
    cost = ut.loss_func(pred, y, loss, datasets,g)
    update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
    summary_op = tf.summary.merge_all()
    with tf.control_dependencies(update_ops):
        optimizer = tf.train.AdamOptimizer(learning_rate=learning_rate).minimize(cost+regu_losses)

    # Initializing the variables
    init = tf.global_variables_initializer()

    # Launch the graph
    gpu_options = tf.GPUOptions(per_process_gpu_memory_fraction=0.2)
    with tf.Session(config=tf.ConfigProto(gpu_options=gpu_options)) as sess:
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