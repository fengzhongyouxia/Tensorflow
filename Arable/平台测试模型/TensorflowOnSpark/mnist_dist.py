# -*- coding:utf-8 -*-
# Copyright 2017 Yahoo Inc.
# Licensed under the terms of the Apache 2.0 license.
# Please see LICENSE file in the project root for terms.

# Distributed MNIST on grid based on TensorFlow MNIST example

from __future__ import absolute_import
from __future__ import division
from __future__ import nested_scopes
from __future__ import print_function
# import logging

# log = logging.getLogger(__name__)

def print_log(worker_num, arg): # 打印信息
  print("{0}: {1}".format(worker_num, arg))
  # log.info("{0}: {1}".format(worker_num, arg))

def map_fun(args, ctx):
  # from com.yahoo.ml.tf import TFNode
  from tensorflowonspark import TFNode
  from datetime import datetime
  import math
  import numpy
  import tensorflow as tf
  import time

  worker_num = ctx.worker_num #worker数量
  job_name = ctx.job_name # job名
  task_index = ctx.task_index # 任务索引
  cluster_spec = ctx.cluster_spec # 集群

  IMAGE_PIXELS=10 # 图像大小 mnist 28x28x1  (后续参考自己图像大小进行修改)
  channels=3
  num_class=2
  dropout = 0.7
  learning_rate=1e-4

  # Delay PS nodes a bit, since workers seem to reserve GPUs more quickly/reliably (w/o conflict)
  if job_name == "ps": # ps节点(主节点)
    time.sleep((worker_num + 1) * 5)

  # Parameters
  hidden_units = 128 # NN隐藏层
  batch_size   = args.batch_size #每批次训练的样本数

  # Get TF cluster and server instances
  cluster, server = TFNode.start_cluster_server(ctx, 1, args.rdma)

  def feed_dict(batch):
    # Convert from [(images, labels)] to two numpy arrays of the proper type
    images = []
    labels = []
    for item in batch:
      images.append(item[0])
      labels.append(item[1])
    xs = numpy.array(images)
    xs = xs.astype(numpy.float32)
    xs = xs/255.0 # 数据归一化
    ys = numpy.array(labels)
    ys = ys.astype(numpy.uint8)
    return (xs, ys)

  if job_name == "ps":
    server.join()
  elif job_name == "worker":

    # Assigns ops to the local worker by default.
    with tf.device(tf.train.replica_device_setter(
        worker_device="/job:worker/task:%d" % task_index,
        cluster=cluster)):

      #-------------普通的NN模型(可以修改成自己的模型)---------------------------------#
      #↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓#
      '''
      # Variables of the hidden layer
      hid_w = tf.Variable(tf.truncated_normal([IMAGE_PIXELS * IMAGE_PIXELS, hidden_units],
                              stddev=1.0 / IMAGE_PIXELS), name="hid_w")
      hid_b = tf.Variable(tf.zeros([hidden_units]), name="hid_b")
      # tf.summary.histogram("hidden_weights", hid_w)

      # Variables of the softmax layer
      sm_w = tf.Variable(tf.truncated_normal([hidden_units, 10],
                              stddev=1.0 / math.sqrt(hidden_units)), name="sm_w")
      sm_b = tf.Variable(tf.zeros([10]), name="sm_b")
      # tf.summary.histogram("softmax_weights", sm_w)
      '''

      # Create some wrappers for simplicity
      def conv2d(x, W, b, strides=1):
        # Conv2D wrapper, with bias and relu activation
        x = tf.nn.conv2d(x, W, strides=[1, strides, strides, 1], padding='SAME')
        x = tf.nn.bias_add(x, b)  # strides中间两个为1 表示x,y方向都不间隔取样
        return tf.nn.relu(x)

      def maxpool2d(x, k=2):
        # MaxPool2D wrapper
        return tf.nn.max_pool(x, ksize=[1, k, k, 1], strides=[1, k, k, 1],
                              padding='SAME')  # strides中间两个为2 表示x,y方向都间隔1个取样

      # Store layers weight & bias
      weights = {
        # 5x5 conv, 3 input, 32 outputs 彩色图像3个输入(3个频道)，灰度图像1个输入
        'wc1': tf.Variable(tf.random_normal([5, 5, channels, 32])),  # 5X5的卷积模板
        # 5x5 conv, 32 inputs, 64 outputs
        'wc2': tf.Variable(tf.random_normal([5, 5, 32, 64])),
        # fully connected, 7*7*64 inputs, 1024 outputs
        'wd1': tf.Variable(tf.random_normal([(1+IMAGE_PIXELS // 4) * (1+IMAGE_PIXELS // 4) * 64, 1024])),
        # 1024 inputs, 10 outputs (class prediction)
        'out': tf.Variable(tf.random_normal([1024, num_class]))
      }

      biases = {
        'bc1': tf.Variable(tf.random_normal([32])),
        'bc2': tf.Variable(tf.random_normal([64])),
        'bd1': tf.Variable(tf.random_normal([1024])),
        'out': tf.Variable(tf.random_normal([num_class]))
      }


      # Placeholders or QueueRunner/Readers for input data
      x = tf.placeholder(tf.float32, [None, IMAGE_PIXELS * IMAGE_PIXELS*channels], name="x") # mnist 28*28*1
      y_ = tf.placeholder(tf.float32, [None, num_class], name="y_")

      x_img = tf.reshape(x, [-1, IMAGE_PIXELS, IMAGE_PIXELS, channels]) # mnist 数据 28x28x1 (灰度图 波段为1)
      # tf.summary.image("x_img", x_img)

      # 改成卷积模型
      conv1 = conv2d(x_img, weights['wc1'], biases['bc1'])
      conv1 = maxpool2d(conv1, k=2)
      conv2 = conv2d(conv1, weights['wc2'], biases['bc2'])
      conv2 = maxpool2d(conv2, k=2)
      fc1 = tf.reshape(conv2, [-1, weights['wd1'].get_shape().as_list()[0]])
      fc1 = tf.add(tf.matmul(fc1, weights['wd1']), biases['bd1'])
      fc1 = tf.nn.relu(fc1)
      if args.mode == "train":
        fc1 = tf.nn.dropout(fc1, dropout)
      y = tf.add(tf.matmul(fc1, weights['out']), biases['out'])

      '''
      hid_lin = tf.nn.xw_plus_b(x, hid_w, hid_b) # tf.nn.add(tf.nn.matmul(x,hid_w),hid_b)
      hid = tf.nn.relu(hid_lin)

      y = tf.nn.softmax(tf.nn.xw_plus_b(hid, sm_w, sm_b))
      '''
      # global_step = tf.Variable(0)

      global_step = tf.Variable(0, name="global_step", trainable=False)

      # loss = -tf.reduce_sum(y_ * tf.log(tf.clip_by_value(y, 1e-10, 1.0)))

      loss=tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(labels=y_,logits=y))

      # tf.summary.scalar("loss", loss)

      train_op = tf.train.AdagradOptimizer(learning_rate).minimize(
          loss, global_step=global_step)

      # Test trained model
      label = tf.argmax(y_, 1, name="label")
      prediction = tf.argmax(y, 1,name="prediction")
      correct_prediction = tf.equal(prediction, label)

      accuracy = tf.reduce_mean(tf.cast(correct_prediction, tf.float32), name="accuracy")
      # tf.summary.scalar("acc", accuracy)

      saver = tf.train.Saver()
      # summary_op = tf.summary.merge_all()
      init_op = tf.global_variables_initializer()

      # ↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑#
      #---------------上面的模型可以修改成自己的模型------------------------------#

    # Create a "supervisor", which oversees the training process and stores model state into HDFS
    logdir = TFNode.hdfs_path(ctx, args.model)
    print("tensorflow model path: {0}".format(logdir)) #
    # log.info("tensorflow model path: {0}".format(logdir))
    # summary_writer = tf.summary.FileWriter("tensorboard_%d" %(worker_num), graph=tf.get_default_graph())

    if args.mode == "train":
      sv = tf.train.Supervisor(is_chief=(task_index == 0),
                               logdir=logdir,
                               init_op=init_op,
                               # summary_op=None,
                               saver=saver,
                               # recovery_wait_secs=1,
                               global_step=global_step,
                               stop_grace_secs=300,
                               save_model_secs=10)
    else:
      sv = tf.train.Supervisor(is_chief=(task_index == 0),
                               logdir=logdir,
                               # summary_op=None,
                               saver=saver,
                               # recovery_wait_secs=1,
                               global_step=global_step,
                               stop_grace_secs=300,
                               save_model_secs=0)

    # The supervisor takes care of session initialization, restoring from
    # a checkpoint, and closing when done or an error occurs.
    with sv.managed_session(server.target) as sess: # 打开session
      # logging.basicConfig(level=logging.INFO)

      print("{0} session ready".format(datetime.now().isoformat()))
      # log.info("{0} session ready".format(datetime.now().isoformat()))
      # Loop until the supervisor shuts down or 1000000 steps have completed.
      step = 0
      tf_feed = TFNode.DataFeed(ctx.mgr, args.mode == "train")
      while not sv.should_stop() and not tf_feed.should_stop() and step < args.steps:
        # Run a training step asynchronously.
        # See `tf.train.SyncReplicasOptimizer` for additional details on how to
        # perform *synchronous* training.

        # using feed_dict
        batch_xs, batch_ys = feed_dict(tf_feed.next_batch(batch_size))
        feed = {x: batch_xs, y_: batch_ys}

        if len(batch_xs) > 0:
          if args.mode == "train":
            # _, summary, step = sess.run([train_op, summary_op, global_step], feed_dict=feed)
            _, step = sess.run([train_op,  global_step], feed_dict=feed)
            # print accuracy and save model checkpoint to HDFS every 100 steps
            if (step % 100 == 0):
              print("{0} step: {1} accuracy: {2}".format(datetime.now().isoformat(), step, sess.run(accuracy,{x: batch_xs, y_: batch_ys})))
              # log.info("{0} step: {1} accuracy: {2}".format(datetime.now().isoformat(), step, sess.run(accuracy,{x: batch_xs, y_: batch_ys})))
            if sv.is_chief:
              pass
              # summary_writer.add_summary(summary, step)
          else: # args.mode == "inference"
            labels, preds, acc = sess.run([label, prediction, accuracy], feed_dict=feed)

            results = ["{0} Label: {1}, Prediction: {2}".format(datetime.now().isoformat(), l, p) for l,p in zip(labels,preds)]
            tf_feed.batch_results(results)
            print("acc: {0}".format(acc))
            # log.info("acc: {0}".format(acc))
      if sv.should_stop() or step >= args.steps:
        tf_feed.terminate()

    # Ask for all the services to stop.
    print("{0} stopping supervisor".format(datetime.now().isoformat()))
    # log.info("{0} stopping supervisor".format(datetime.now().isoformat()))
    sv.stop()

